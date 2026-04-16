# src/webhook.py
import os
import httpx
from typing import Optional, List, Dict, Any

from qdrant_client import QdrantClient
from .config import (
    QDRANT_URL, QDRANT_API_KEY, QDRANT_COLLECTION,
    GROQ_API_KEY, GROQ_MODEL, GROQ_URL,
    EMBEDDING_MODEL, EMBEDDING_DIM
)

# =============================================================================
# GLOBAL STATE (For MVP - use Redis/Qdrant in production)
# =============================================================================
realtime_context_store: Dict[str, Any] = {}
conversation_history: Dict[str, List[Dict[str, str]]] = {}

# =============================================================================
# QDRANT CLIENT INITIALIZATION
# =============================================================================
if QDRANT_URL:
    try:
        qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    except Exception as e:
        print(f"⚠️ Qdrant connection failed: {e}")
        print("⚠️ Falling back to in-memory Qdrant. Set QDRANT_URL to a running server to use persistence.")
        qdrant_client = QdrantClient(":memory:")
else:
    qdrant_client = QdrantClient(":memory:")
    print("⚠️ Using in-memory Qdrant client (development mode)")

# =============================================================================
# EMBEDDING MODEL (Lazy Loading)
# =============================================================================
_embedder = None

def get_embedder():
    """Lazy initialization of sentence transformer to avoid import issues."""
    global _embedder
    if _embedder is None:
        try:
            import importlib
            sentence_transformers = importlib.import_module("sentence_transformers")
            _embedder = sentence_transformers.SentenceTransformer(EMBEDDING_MODEL)
        except (ImportError, OSError) as e:
            print(f"⚠️ Warning: Could not load sentence-transformers: {e}")
            print("🔄 Using fallback hash-based embeddings")
            _embedder = None
    return _embedder

def create_simple_vector(text: str, dim: int = EMBEDDING_DIM) -> list:
    """Create a simple hash-based vector as fallback."""
    import hashlib
    hash_obj = hashlib.sha256(text.encode())
    hash_bytes = hash_obj.digest()
    vector = [float(b) / 255.0 for b in hash_bytes] * (dim // 32)
    return vector[:dim]

# =============================================================================
# RAG: SEARCH & CONTEXT BUILDING
# =============================================================================
def search_codebase(query: str, limit: int = 3):
    """Search Qdrant for relevant code snippets."""
    try:
        embedder = get_embedder()
        if embedder:
            vector = embedder.encode([query])[0].tolist()
        else:
            vector = create_simple_vector(query)

        results = qdrant_client.query_points(
            collection_name=QDRANT_COLLECTION,
            query=vector,
            limit=limit
        ).points
        return results
    except Exception as e:
        print(f"❌ Search failed: {e}")
        return []

def build_context(results) -> str:
    """Format Qdrant results into LLM-readable context."""
    snippets = []
    for r in results:
        payload = r.payload or {}
        file_path = payload.get('file_path') or payload.get('path', 'unknown')
        snippet = payload.get('content') or payload.get('snippet', '')
        snippets.append(f"File: {file_path}\nCode: {snippet}\n")
    return "\n---\n".join(snippets) if snippets else "No relevant code found."

# =============================================================================
# LLM QUERY FUNCTIONS
# =============================================================================
def query_llm(context: str, user_query: str) -> str:
    """Query Groq LLM with voice-optimized prompt."""
    prompt = f"""You are CodeVox, a voice-first developer assistant.
Respond in 1-2 short sentences optimized for speech.
Avoid markdown, code blocks, or lists. Use natural pauses via commas.
If unsure, ask for clarification.

Context:
{context}

User Query: {user_query}
"""
    return _call_groq_api(prompt)

def query_llm_simple(prompt: str) -> str:
    """Query Groq LLM with a raw prompt string."""
    return _call_groq_api(prompt)

def _call_groq_api(prompt: str) -> str:
    """Internal helper to call Groq API with error handling."""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 150
    }
    
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(GROQ_URL, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"❌ LLM call failed: {e}")
        return "Sorry, I'm having trouble connecting right now. Please try again."

# =============================================================================
# CONTEXT INJECTION (VS Code Extension Integration)
# =============================================================================
def get_realtime_context_injection() -> str:
    """
    Check global store for real-time context from VS Code extension.
    Returns formatted context string or empty string if none available.
    """
    global realtime_context_store
    
    if not realtime_context_store or 'latest' not in realtime_context_store:
        return ""
    
    ctx = realtime_context_store['latest']
    intent = ctx.get('intent', '')
    
    if intent == 'user_selected_code':
        return f"""
[REAL-TIME EDITOR CONTEXT]
The developer is currently viewing this code:
File: {ctx.get('file', 'unknown')}
Code Snippet:
{ctx.get('content', '')}
"""
    elif intent == 'potential_error':
        return f"""
[REAL-TIME DEBUG CONTEXT]
The developer might be debugging this line:
File: {ctx.get('file', 'unknown')}
Code: {ctx.get('line', '')}
"""
    return ""
# Add to src/webhook.py (module level)
def update_realtime_context(context_data: Dict[str, Any]):
    """
    Update the global real-time context store.
    Called by /vapi/context endpoint from VS Code extension.
    """
    global realtime_context_store
    realtime_context_store['latest'] = context_data
    realtime_context_store['timestamp'] = time.time()
    logger.debug(f"📥 Context updated: {context_data.get('intent') or context_data.get('file_name')}")
# =============================================================================
# MAIN HANDLER: Vapi Webhook Entry Point
# =============================================================================
def handle_vapi_message(transcript: str, call_id: str = "default") -> dict:
    """
    Process incoming voice message from Vapi.
    Returns Vapi-compatible response format.
    """
    global conversation_history, realtime_context_store
    
    # 1. Retrieve conversation history for continuity
    history = conversation_history.get(call_id, [])
    history_text = "\n".join([f"{h['role']}: {h['content']}" for h in history[-4:]])
    
    # 2. Search codebase for semantic matches (RAG)
    results = search_codebase(transcript)
    rag_context = build_context(results)
    
    # 3. Get real-time context from VS Code extension (if any)
    realtime_context = get_realtime_context_injection()
    
    # 4. Detect debug intent for specialized handling
    debug_keywords = ["error", "traceback", "exception", "bug", "crash", "failed", "not working", "fix this"]
    is_debug_mode = any(kw in transcript.lower() for kw in debug_keywords)
    
    # 5. Build the final prompt
    if is_debug_mode:
        prompt = f"""You are CodeVox, a senior debugging buddy.
The developer reported: "{transcript}"

{realtime_context}
{rag_context}

Instructions:
1. Explain the ROOT CAUSE in one simple sentence.
2. Provide the FIX clearly (plain English, no code blocks).
3. Be encouraging and concise.
4. Ask if they need the specific code snippet.

Previous conversation (if relevant):
{history_text}
"""
    else:
        prompt = f"""You are CodeVox, a voice-first developer assistant.
Respond in 1-2 short sentences optimized for speech.
Avoid markdown, code blocks, or lists. Use natural pauses via commas.

{realtime_context}
Codebase Context:
{rag_context}

Previous conversation:
{history_text}

User Query: {transcript}
"""
    
    # 6. Query LLM
    response_text = query_llm_simple(prompt)
    
    # 7. Update conversation history
    history.append({"role": "user", "content": transcript})
    history.append({"role": "assistant", "content": response_text})
    conversation_history[call_id] = history
    
    # 8. Return Vapi-compatible response
    return {
        "messages": [
            {
                "role": "assistant",
                "content": response_text
            }
        ]
    }

# =============================================================================
# UTILITY: Update Real-Time Context (Called by FastAPI endpoint)
# =============================================================================
def update_realtime_context(context_data: Dict[str, Any]):
    """
    Update the global real-time context store.
    Called by /vapi/context endpoint from VS Code extension.
    """
    global realtime_context_store
    realtime_context_store['latest'] = context_data
    realtime_context_store['timestamp'] = __import__('time').time()
    print(f"📥 Context updated: {context_data.get('intent', 'unknown')}")