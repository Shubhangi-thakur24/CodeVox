# src/rag/init_qdrant.py
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def init_qdrant_collection():
    """
    Initialize Qdrant collection for CodeVox.
    Creates collection if it doesn't exist, validates connection.
    """
    
    # Get credentials from config
    qdrant_url = os.getenv("QDRANT_URL")
    qdrant_api_key = os.getenv("QDRANT_API_KEY")
    collection_name = os.getenv("QDRANT_COLLECTION", "codevox_codebase")
    
    if not qdrant_url:
        raise ValueError(" Missing QDRANT_URL in .env")
    
    # API key is optional for local Qdrant
    
    print(f" Connecting to Qdrant at: {qdrant_url}")
    
    try:
        # Initialize client
        if qdrant_api_key:
            client = QdrantClient(
                url=qdrant_url,
                api_key=qdrant_api_key,
                timeout=30
            )
        else:
            client = QdrantClient(
                url=qdrant_url,
                timeout=30
            )
        
        # Test connection
        client.get_collections()
        print(" Successfully connected to Qdrant!")
        
        # Check if collection exists
        if client.collection_exists(collection_name):
            print(f"ℹ Collection '{collection_name}' already exists.")
            
            # Get collection info
            collection_info = client.get_collection(collection_name)
            print(f"   - Vectors: {collection_info.points_count}")
            print(f"   - Dimensions: {collection_info.config.params.vectors.size}")
            print(f"   - Distance Metric: {collection_info.config.params.vectors.distance}")
            
            return client
            
        else:
            print(f"Creating new collection: '{collection_name}'...")
            
            # Create collection with optimized settings for code
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=384,              # all-MiniLM-L6-v2 dimension
                    distance=Distance.COSINE,  # Best for semantic similarity
                    on_disk=True           # Save memory for large codebases
                ),
                hnsw_config={
                    "m": 16,               # Higher = better recall, slower build
                    "ef_construct": 128    # Higher = better quality index
                }
            )
            
            print(f"     Collection '{collection_name}' created successfully!")
            print(f"   - Dimensions: 384 (all-MiniLM-L6-v2)")
            print(f"   - Distance: COSINE (semantic similarity)")
            print(f"   - Optimized for code semantic search")
            
            return client
            
    except Exception as e:
        error_message = str(e)
        print(f" Failed to initialize Qdrant: {error_message}")
        if "actively refused" in error_message or "Connection refused" in error_message or "WinError 10061" in error_message:
            print("  → Qdrant is not reachable on localhost:6333.")
            print("  → Start a local Qdrant server before running this script:")
            print("      docker run -p 6333:6333 qdrant/qdrant")
            print("  → Or update QDRANT_URL in .env to point to your running Qdrant instance.")
        raise

def validate_collection(client, collection_name):
    """Validate collection is ready for indexing."""
    try:
        info = client.get_collection(collection_name)
        print(f"\n Collection Status:")
        print(f"   - Name: {collection_name}")
        print(f"   - Points: {info.points_count}")
        print(f"   - Vectors: {info.config.params.vectors.size}d")
        print(f"   - Status: Ready for indexing")
        return True
    except Exception as e:
        print(f" Validation failed: {e}")
        return False

if __name__ == "__main__":
    print(" Initializing CodeVox Qdrant Database...")
    print("=" * 50)
    
    try:
        client = init_qdrant_collection()
        collection_name = os.getenv("QDRANT_COLLECTION", "codevox_codebase")
        
        if validate_collection(client, collection_name):
            print("\nQdrant database is ready!")
            print("Next step: Run the indexer to populate with code.")
        else:
            print("\n Database initialized but validation failed.")
            sys.exit(1)
            
    except Exception as e:
        print(f"\nInitialization failed: {e}")
        sys.exit(1)