# src/webhook_server.py
import os
import sys
import json
import time
import logging
import signal
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi.responses import FileResponse

# Load environment variables FIRST
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("codevox_server.log", mode="a", encoding="utf-8")
    ]
)
logger = logging.getLogger("CodeVox")

# =============================================================================
# CREATE FASTAPI APP FIRST (Critical: must happen before any app.mount() calls)
# =============================================================================
app = FastAPI(
    title="CodeVox Webhook Server",
    description="Voice-first developer assistant backend",
    version="1.0.0"
)

# =============================================================================
# MOUNT STATIC FILES (UI) - After app is created
# =============================================================================
# Build path to ui/ folder (project_root/ui)
try:
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    UI_DIR = project_root / "ui"
    
    if UI_DIR.exists():
        app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")
        logger.info(f"✅ UI mounted at /ui from {UI_DIR}")
    else:
        logger.warning(f"⚠️ UI directory not found: {UI_DIR}")
except Exception as e:
    logger.error(f"❌ Failed to mount UI: {e}")

# =============================================================================
# GLOBAL STATE (MVP - use Redis/Qdrant in production)
# =============================================================================
realtime_context_store: Dict[str, Any] = {}

# =============================================================================
# PYDANTIC MODELS
# =============================================================================
class ContextPayload(BaseModel):
    """Payload schema for /vapi/context endpoint."""
    type: Optional[str] = None
    data: Optional[Dict[str, Any]] = None  # ✅ Added missing 'data' field name
    
    # Allow extra fields for flexibility (MVP)
    class Config:
        extra = "allow"

# =============================================================================
# UTILITY ENDPOINTS
# =============================================================================
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return JSONResponse(content={"detail": "No favicon"}, status_code=404)

@app.get("/")
async def root():
    return {
        "service": "CodeVox",
        "status": "running",
        "version": "1.0.0",
        "endpoints": {
            "POST /vapi/webhook": "Vapi voice assistant webhook",
            "POST /vapi/context": "VS Code extension context updates",
            "GET /health": "Health check",
            "GET /ui": "Voice assistant UI"
        }
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "context_store_active": bool(realtime_context_store)
    }

# =============================================================================
# VS CODE EXTENSION: REAL-TIME CONTEXT ENDPOINT
# =============================================================================
@app.post("/vapi/context")
async def receive_context(request: Request):
    try:
        raw = await request.json()
        
        # Accept both wrapped {"type", "data"} and direct payload
        context_data = raw.get("data", raw)
        payload_type = raw.get("type", "unknown")
        
        logger.info(f"Received {payload_type}: file={context_data.get('file_name')}")
        
        global realtime_context_store
        realtime_context_store = {
            "latest": context_data,
            "timestamp": datetime.now().isoformat(),
            "type": payload_type
        }
        
        return {"status": "received", "message": "Context updated"}
        
    except Exception as e:
        logger.error(f" Context error: {e}")
        return {"status": "error", "message": str(e)}, 400
# =============================================================================
# VAPI WEBHOOK: MAIN VOICE HANDLER
# =============================================================================
@app.post("/vapi/webhook")
async def vapi_webhook(request: Request):
    start_time = time.time()
    
    try:
        data = await request.json()
        
        # Logging (free analytics)
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": data.get("type"),
            "role": data.get("message", {}).get("role"),
            "transcript": data.get("message", {}).get("content", "")[:200],
            "call_id": data.get("call", {}).get("id", "unknown"),
        }
        try:
            with open("call_logs.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception:
            pass
        
        # Filter: Only process user messages
        if data.get("type") != "message":
            return JSONResponse(content={"status": "ignored", "reason": "not_a_message"})
            
        message_data = data.get("message", {})
        if message_data.get("role") != "user":
            return JSONResponse(content={"status": "ignored", "reason": "not_user_message"})
        
        transcript = message_data.get("content", "").strip()
        call_id = data.get("call", {}).get("id", "default_session")
        
        if not transcript:
            return JSONResponse(content={
                "messages": [{"role": "assistant", "content": "I didn't catch that. Could you repeat?"}]
            })
        
        logger.info(f"🎙️ Received (call={call_id}): '{transcript[:80]}...'")
        
        # Wake word filter (credit saver)
        wake_words = ["hey codevox", "codevox", "ok codevox"]
        is_activated = any(ww in transcript.lower() for ww in wake_words)
        
        if not is_activated:
            latency = time.time() - start_time
            logger.info(f"⛔ Blocked (no wake word). Latency: {latency*1000:.1f}ms")
            return JSONResponse(content={
                "messages": [{
                    "role": "assistant",
                    "content": "I'm listening. Please say 'Hey CodeVox' to activate me."
                }]
            })
        
        # Prepare: Clean query and detect intent
        clean_query = transcript
        for ww in wake_words:
            clean_query = clean_query.lower().replace(ww, "").strip()
        
        debug_keywords = ["error", "traceback", "exception", "bug", "crash", "failed", "not working", "fix this", "broken", "issue"]
        is_debug_mode = any(kw in clean_query.lower() for kw in debug_keywords)
        
        mode_str = "DEBUG" if is_debug_mode else "STANDARD"
        logger.info(f"✅ Activated! Mode: {mode_str}, Query: '{clean_query[:60]}...'")
        
        # Process: RAG Pipeline via webhook.py
        from src.webhook import handle_vapi_message
        response = handle_vapi_message(clean_query, call_id)
        
        # Return: Vapi-compatible response
        total_latency = time.time() - start_time
        response_preview = response.get("messages", [{}])[0].get("content", "")[:50]
        logger.info(f"⚡ Response ready in {total_latency*1000:.1f}ms: '{response_preview}...'")
        
        return JSONResponse(content=response)
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ Invalid JSON in webhook: {e}")
        return JSONResponse(content={
            "messages": [{"role": "assistant", "content": "Sorry, I couldn't understand that. Please try again."}]
        }, status_code=400)
        
    except Exception as e:
        import traceback
        logger.error(f"❌ Webhook error: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse(content={
            "messages": [{"role": "assistant", "content": "Sorry, I hit a snag. Please try your question again."}]
        }, status_code=200)

@app.get("/vapi/webhook")
async def vapi_webhook_info():
    return {
        "status": "ready",
        "message": "This endpoint accepts POST only. Send Vapi webhook payloads to /vapi/webhook.",
        "example": {
            "type": "message",
            "message": {"role": "user", "content": "Hey CodeVox, explain this function"}
        }
    }

# =============================================================================
# CORS Middleware (for local development)
# =============================================================================
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# SERVER ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    reload = os.getenv("ENV", "development") == "development"
    
    logger.info(f" Starting CodeVox Server on port {port}")
    
    uvicorn.run(
        "src.webhook_server:app",
        host="0.0.0.0",
        port=port,
        reload=reload,
        log_level="info"
    )