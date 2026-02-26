from pathlib import Path
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

def search_kb(query: str, model_name: str, index_dir: str = "app/semantic/.index", k: int = 3) -> list[str]:
    index_path = Path(index_dir) / "kb.faiss"
    chunks_path = Path(index_dir) / "chunks.txt"
    if not index_path.exists() or not chunks_path.exists():
        return ["Knowledge base index not built yet. Run: python -m app.main build-kb-index"]

    chunks = chunks_path.read_text(encoding="utf-8").split("\n\n---\n\n")
    model = SentenceTransformer(model_name)
    q = model.encode([query], normalize_embeddings=True).astype(np.float32)

    index = faiss.read_index(str(index_path))
    scores, ids = index.search(q, k)
    results = []
    for i in ids[0]:
        if 0 <= i < len(chunks):
            results.append(chunks[i])
    return results
