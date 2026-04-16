# src/config.py
import os
from dotenv import load_dotenv

load_dotenv()

# Qdrant
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "codevox_collection")

# LLM (Groq - Free Tier)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Vapi
VAPI_ASSISTANT_ID = os.getenv("VAPI_ASSISTANT_ID")

# Embedding Model (Local, Free)
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384