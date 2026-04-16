# verify_index.py
import os
from qdrant_client import QdrantClient
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()

client = QdrantClient(url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_API_KEY"))
collection = os.getenv("QDRANT_COLLECTION", "codevox_codebase")
embedder = SentenceTransformer("all-MiniLM-L6-v2")

# Test Search
query = "authentication login"
vector = embedder.encode(query).tolist()

results = client.query_points(
    collection_name=collection,
    query=vector,
    limit=3
)

print(f" Searching for: '{query}'")
print("-" * 40)
for r in results.points:
    print(f"File: {r.payload['file_path']}")
    print(f"Snippet: {r.payload['content'][:100]}...")
    print(f"Score: {r.score:.4f}")
    print("-" * 20)