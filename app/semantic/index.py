from pathlib import Path
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

def build_index(kb_path: str, model_name: str, out_dir: str = "app/semantic/.index"):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    text = Path(kb_path).read_text(encoding="utf-8")
    chunks = [c.strip() for c in text.split("\n## ") if c.strip()]
    # restore the header marker to keep context
    chunks = ["## " + c for c in chunks]

    model = SentenceTransformer(model_name)
    emb = model.encode(chunks, normalize_embeddings=True)

    dim = emb.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(emb.astype(np.float32))

    faiss.write_index(index, str(out / "kb.faiss"))
    (out / "chunks.txt").write_text("\n\n---\n\n".join(chunks), encoding="utf-8")
