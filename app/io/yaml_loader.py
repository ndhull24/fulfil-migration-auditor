from __future__ import annotations
from typing import Any, Dict, Tuple
import pandas as pd
import yaml

def load_demo_yaml(file_obj) -> Tuple[Dict[str, pd.DataFrame], Dict[str, str]]:
    """
    Expects YAML structure:
    products: [ ... ]
    orders: [ ... ]
    sku_map: [ {old_sku, new_sku}, ... ] (optional)

    Returns:
      tables: {"products": df_products, "orders": df_orders}
      sku_map_dict: {"OLD": "NEW", ...}
    """
    raw = yaml.safe_load(file_obj)
    if not isinstance(raw, dict):
        raise ValueError("YAML root must be a dictionary with keys: products, orders (and optional sku_map).")

    products = raw.get("products") or []
    orders = raw.get("orders") or []
    sku_map = raw.get("sku_map") or []

    dfp = pd.DataFrame(products).fillna("")
    dfo = pd.DataFrame(orders).fillna("")

    sku_map_dict: Dict[str, str] = {}
    for row in sku_map:
        if not isinstance(row, dict):
            continue
        old = str(row.get("old_sku", "")).strip().upper()
        new = str(row.get("new_sku", "")).strip().upper()
        if old and new:
            sku_map_dict[old] = new

    tables = {"products": dfp, "orders": dfo}
    return tables, sku_map_dict
