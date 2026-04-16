"""
Script to create/update Vapi assistant via API.
Run ONCE before starting CodeVox.

Usage: python scripts/setup_vapi_assistant.py
"""
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

VAPI_PRIVATE_API = os.getenv("VAPI_PRIVATE_API", "")
CODEVOX_API_URL  = os.getenv("CODEVOX_API_URL", "http://localhost:8000")
VAPI_ASSISTANT_ID = os.getenv("VAPI_ASSISTANT_ID", "")

# ── Assistant config ──────────────────────────────────────────────────────────
ASSISTANT_CONFIG = {
    "name": "CodeVox",
    "firstMessage": "Hey, I'm CodeVox. What are you working on?",

    # Use Groq for FREE LLM (Vapi supports it as provider)
    # This conserves your $30 — you only pay for STT + TTS
    "model": {
        "provider": "groq",
        "model": "llama3-8b-8192",
        "systemPrompt": (
            "You are CodeVox, a senior developer assistant that responds by voice. "
            "Be concise (2-3 sentences max). Give fixes, not just diagnoses. "
            "When you need to search the codebase, use the search_codebase tool. "
            "Proactively mention IDE errors you detect."
        ),
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "search_codebase",
                    "description": "Search the indexed codebase for relevant code snippets.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "What to search for"}
                        },
                        "required": ["query"]
                    },
                    "server": {"url": f"{CODEVOX_API_URL}/vapi/webhook"}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "explain_current_errors",
                    "description": "Explain the current IDE errors in the developer's editor.",
                    "parameters": {"type": "object", "properties": {}},
                    "server": {"url": f"{CODEVOX_API_URL}/vapi/webhook"}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_editor_context",
                    "description": "Get the code the developer is currently looking at.",
                    "parameters": {"type": "object", "properties": {}},
                    "server": {"url": f"{CODEVOX_API_URL}/vapi/webhook"}
                }
            },
        ]
    },

    # PlayHT is cheaper than ElevenLabs — saves $30 budget
    "voice": {
        "provider": "playht",
        "voiceId": "jennifer"
    },

    # Webhook for all events
    "serverUrl": f"{CODEVOX_API_URL}/vapi/webhook",

    # Transcriber
    "transcriber": {
        "provider": "deepgram",
        "model": "nova-2",
        "language": "en"
    },

    # Silence detection — end turn after 0.8s silence
    "silenceTimeoutSeconds": 30,
    "maxDurationSeconds": 600,
    "backgroundSound": "off",
}


def create_or_update():
    headers = {
        "Authorization": f"Bearer {VAPI_PRIVATE_API}",
        "Content-Type": "application/json",
    }

    if VAPI_ASSISTANT_ID:
        # Update existing
        url = f"https://api.vapi.ai/assistant/{VAPI_ASSISTANT_ID}"
        resp = requests.patch(url, headers=headers, json=ASSISTANT_CONFIG)
        action = "Updated"
    else:
        # Create new
        url = "https://api.vapi.ai/assistant"
        resp = requests.post(url, headers=headers, json=ASSISTANT_CONFIG)
        action = "Created"

    if resp.status_code in (200, 201):
        data = resp.json()
        print(f"✓ {action} Vapi assistant: {data.get('id')}")
        print(f"\nAdd to your .env:")
        print(f"VAPI_ASSISTANT_ID={data.get('id')}")
    else:
        print(f"✗ Failed ({resp.status_code}): {resp.text}")


if __name__ == "__main__":
    if not VAPI_PRIVATE_API:
        print("ERROR: VAPI_PRIVATE_API not set in .env")
        exit(1)
    create_or_update()