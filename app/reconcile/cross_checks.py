from typing import Dict, List, Optional
import pandas as pd
from app.rules.base import Finding
from app.reconcile.sku_map import map_sku

def _norm_sku(s: str) -> str:
    return str(s).strip().upper()

def orders_reference_existing_skus(
    all_tables: Dict[str, pd.DataFrame],
    sku_map: Optional[Dict[str, str]] = None
) -> List[Finding]:
    f: List[Finding] = []
    sku_map = sku_map or {}

    products = all_tables.get("products")
    orders = all_tables.get("orders")
    if products is None or orders is None:
        return f
    if "sku" not in products.columns or "sku" not in orders.columns:
        return f

    prod_norm = set(_norm_sku(x) for x in products["sku"].astype(str).tolist() if str(x).strip())

    for idx in orders.index.tolist():
        raw = str(orders.loc[idx, "sku"])
        mapped, changed = map_sku(raw, sku_map)
        if changed:
            f.append(Finding(
                entity="orders", severity="SUGGEST", code="SKU_MAPPED",
                message="SKU can be mapped to a canonical SKU using sku_map.csv.",
                row=int(idx), field="sku", value=raw,
                fix=f"Map '{raw}' → '{mapped}' (and keep consistent across all files)."
            ))

        if mapped and mapped not in prod_norm:
            f.append(Finding(
                entity="orders", severity="ERROR", code="SKU_NOT_FOUND",
                message="Order references a SKU that does not exist in products file (after normalization/mapping).",
                row=int(idx), field="sku", value=raw,
                fix="Add the SKU to products OR correct the SKU in orders OR add a sku_map mapping."
            ))

    return f
