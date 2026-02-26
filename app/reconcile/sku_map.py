import pandas as pd
from typing import Dict, Tuple

def load_sku_map(path: str) -> Dict[str, str]:
    df = pd.read_csv(path, dtype=str).fillna("")
    if "old_sku" not in df.columns or "new_sku" not in df.columns:
        raise ValueError("sku_map.csv must have columns: old_sku,new_sku")
    m = {}
    for _, r in df.iterrows():
        old = str(r["old_sku"]).strip().upper()
        new = str(r["new_sku"]).strip().upper()
        if old and new:
            m[old] = new
    return m

def map_sku(raw: str, sku_map: Dict[str, str]) -> Tuple[str, bool]:
    """
    Returns (mapped_sku, changed?)
    """
    s = str(raw).strip().upper()
    if not s:
        return s, False
    if s in sku_map:
        return sku_map[s], True
    return s, False
