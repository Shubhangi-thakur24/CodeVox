# src/rag/indexer.py
import os
import sys
import uuid
import time
import hashlib
from pathlib import Path
from typing import List, Dict, Any
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Distance, VectorParams

# Load config
load_dotenv()

model = SentenceTransformer("all-MiniLM-L6-v2")
class CodeIndexer:
    def __init__(self):
        # Config
        self.qdrant_url = os.getenv("QDRANT_URL")
        self.qdrant_api_key = os.getenv("QDRANT_API_KEY")
        self.collection_name = os.getenv("QDRANT_COLLECTION", "codevox_codebase")
        self.target_dir = os.getenv("TARGET_REPO", ".")  # Default to current dir
        
        # Excluded directories (standard dev ignore list)
        self.exclude_dirs = {
            ".git", "node_modules", "__pycache__", "venv", ".venv", 
            "dist", "build", ".idea", ".vscode", "target", "out", 
            "coverage", ".next", ".nuxt", "vendor"
        }
        
        # Supported extensions
        self.supported_exts = {
            ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".java", 
            ".cpp", ".c", ".h", ".cs", ".rb", ".php", ".rs", ".swift",
            ".kt", ".scala", ".sql", ".md"
        }
        
        # Initialize clients
        print(" Initializing Qdrant Client...")
        self.client = QdrantClient(url=self.qdrant_url, api_key=self.qdrant_api_key)
        
        print(" Loading Embedding Model (all-MiniLM-L6-v2)...")
        # This downloads once, then loads from cache locally
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")
        
        if not self.client.collection_exists(self.collection_name):
            raise ValueError(f" Collection '{self.collection_name}' not found! Run init_qdrant.py first.")
            
        print(f"Indexer Ready. Target: {os.path.abspath(self.target_dir)}")

    def _get_file_hash(self, content: str) -> str:
        """Generate a unique ID based on file path + content hash."""
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def _chunk_code(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """
        Simple chunking strategy:
        1. Split by double newlines (blocks)
        2. If block > 500 chars, split by single newlines
        3. Keep chunks between 50-500 chars
        """
        chunks = []
        
        # Strategy A: Split by logical blocks (functions/classes separated by blank lines)
        raw_blocks = content.split('\n\n')
        
        for block in raw_blocks:
            block = block.strip()
            if len(block) < 30: continue # Skip tiny fragments
            
            if len(block) > 500:
                # Strategy B: Split large blocks by lines
                lines = block.split('\n')
                current_chunk = []
                current_len = 0
                
                for line in lines:
                    if current_len + len(line) > 450 and current_chunk:
                        # Save current chunk
                        chunks.append({
                            "text": "\n".join(current_chunk),
                            "meta": {"type": "block"}
                        })
                        current_chunk = [line]
                        current_len = len(line)
                    else:
                        current_chunk.append(line)
                        current_len += len(line)
                
                if current_chunk:
                    chunks.append({
                        "text": "\n".join(current_chunk),
                        "meta": {"type": "block"}
                    })
            else:
                chunks.append({
                    "text": block,
                    "meta": {"type": "block"}
                })
                
        return chunks

    def scan_directory(self) -> List[PointStruct]:
        """Scan target directory and prepare points for upsert."""
        points = []
        file_count = 0
        chunk_count = 0
        
        print(f" Scanning directory: {self.target_dir}")
        
        for root, dirs, files in os.walk(self.target_dir):
            # Filter out excluded directories
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext not in self.supported_exts:
                    continue
                
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, self.target_dir)
                
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    if not content.strip():
                        continue
                        
                    file_count += 1
                    
                    # Chunk the file
                    chunks = self._chunk_code(content, file_path)
                    
                    for i, chunk_data in enumerate(chunks):
                        chunk_text = chunk_data["text"]
                        
                        # Generate unique ID: filepath + chunk_index + content_hash
                        # This ensures idempotency (re-running won't duplicate)
                        unique_id_str = f"{relative_path}:{i}:{self._get_file_hash(chunk_text)}"
                        point_id = abs(hash(unique_id_str)) % (10**18) # Qdrant needs int or string UUID
                        point_id_str = str(point_id)
                        
                        # Generate embedding
                        vector = self.embedder.encode(chunk_text).tolist()
                        
                        # Prepare payload
                        payload = {
                            "file_path": relative_path,
                            "language": ext.lstrip('.'),
                            "chunk_index": i,
                            "content": chunk_text[:400], # Store snippet for preview
                            "full_hash": self._get_file_hash(content)
                        }
                        
                        points.append(PointStruct(
                            id=point_id_str,
                            vector=vector,
                            payload=payload
                        ))
                        chunk_count += 1
                        
                except Exception as e:
                    print(f" Error reading {file_path}: {e}")
                    
        print(f" Scan Complete: {file_count} files, {chunk_count} chunks generated.")
        return points

    def index_codebase(self, batch_size: int = 64):
        """Upsert all points to Qdrant in batches."""
        points = self.scan_directory()
        
        if not points:
            print(" No code chunks found to index.")
            return
            
        total_points = len(points)
        print(f" Uploading {total_points} vectors to Qdrant...")
        
        start_time = time.time()
        
        for i in range(0, total_points, batch_size):
            batch = points[i:i+batch_size]
            self.client.upsert(
                collection_name=self.collection_name,
                points=batch
            )
            progress = min(i + batch_size, total_points)
            print(f"   ⏳ Uploaded {progress}/{total_points} ({progress/total_points*100:.1f}%)")
            
        elapsed = time.time() - start_time
        print(f" Indexing Complete!")
        print(f"   - Total Vectors: {total_points}")
        print(f"   - Time Taken: {elapsed:.2f}s")
        print(f"   - Avg Speed: {total_points/elapsed:.1f} vectors/sec")
        
        # Verify count
        count = self.client.count(collection_name=self.collection_name)
        print(f"   - DB Total Count: {count.count}")

if __name__ == "__main__":
    print("  Starting CodeVox Codebase Indexer...")
    print("=" * 50)
    
    try:
        indexer = CodeIndexer()
        indexer.index_codebase()
        print("\n Your codebase is now searchable via Voice!")
    except Exception as e:
        print(f"\n Indexing failed: {e}")
        sys.exit(1)