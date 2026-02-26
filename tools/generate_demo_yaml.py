from __future__ import annotations

import random
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

random.seed(42)

CHANNELS = ["Shopify", "Amazon", "Wholesale"]
WAREHOUSES = ["WH-1", "WH-2", "WH-3"]
STATUSES = ["open", "fulfilled", "cancelled", "paid"]
CATEGORIES = ["Apparel", "Accessories", "Footwear", "Home", "Electronics"]
BRANDS = ["Acme", "Nova", "Peak", "Zenith"]
UOMS = ["ea", "box", "case", "pack"]

def rand_date(start: datetime, end: datetime) -> str:
    delta = end - start
    d = start + timedelta(days=random.randint(0, delta.days))
    return d.strftime("%Y-%m-%d")

def make_products(n_products: int) -> list[dict]:
    products = []
    base_barcode = 889900000

    for i in range(n_products):
        sku = f"SKU-{1000+i}"
        products.append({
            "product_id": f"PROD-{1000+i}",   # Stable ID across bad/good files
            "sku": sku,
            "name": f"Product {i}",
            "uom": random.choice(UOMS),
            "status": "active",
            "cost": round(random.uniform(1.0, 50.0), 2),
            "price": round(random.uniform(10.0, 150.0), 2),
            "barcode": str(base_barcode + i),
            "category": random.choice(CATEGORIES),
            "brand": random.choice(BRANDS),
        })

    return products

def make_orders(n_orders: int, product_skus: list[str]) -> list[dict]:
    orders = []
    start = datetime(2024, 1, 1)
    end = datetime(2025, 12, 31)

    for i in range(n_orders):
        sku = random.choice(product_skus)
        orders.append({
            "order_row_id": f"OL-{900000+i}",  # Stable row ID
            "order_id": f"ORD-{900000+i}",
            "order_date": rand_date(start, end),
            "channel": random.choice(CHANNELS),
            "customer_id": f"CUST-{random.randint(1, 2000):04d}",
            "sku": sku,
            "quantity": random.randint(1, 10),
            "warehouse": random.choice(WAREHOUSES),
            "status": random.choice(STATUSES),
        })

    return orders

def inject_issues(products: list[dict], orders: list[dict]) -> dict:
    """
    Mutates products/orders to add realistic migration issues.
    Returns a sku_map that can fix some issues.
    """
    sku_map = []

    # 1) Duplicate SKU: add a duplicate record (different product_id)
    dup = deepcopy(products[10])
    dup["product_id"] = "PROD-DUP-0001"
    dup["name"] = "Duplicate SKU Record"
    products.append(dup)

    # 2) Whitespace SKU in products (canonical should be SKU-xxxx)
    # Example: SKU-1025 -> "SKU 1025"
    if len(products) > 25:
        original = products[25]["sku"]  # SKU-1025
        products[25]["sku"] = original.replace("-", " ")
        sku_map.append({"old_sku": products[25]["sku"], "new_sku": original})

    # 3) Blank UOM
    if len(products) > 40:
        products[40]["uom"] = ""

    # 4) Blank name
    if len(products) > 60:
        products[60]["name"] = ""

    # 5) Duplicate barcode
    if len(products) > 72:
        products[70]["barcode"] = products[71]["barcode"]

    # Orders issues
    # A) SKU not found
    if len(orders) > 15:
        orders[15]["sku"] = "SKU-999999"

    # B) SKU with whitespace that should map
    if len(orders) > 30:
        old = orders[30]["sku"].replace("-", " ")
        new = orders[30]["sku"]
        orders[30]["sku"] = old
        sku_map.append({"old_sku": old, "new_sku": new})

    # C) Invalid date
    if len(orders) > 45:
        orders[45]["order_date"] = "2025-99-99"

    # D) quantity 0
    if len(orders) > 55:
        orders[55]["quantity"] = 0

    # E) Negative quantity
    if len(orders) > 65:
        orders[65]["quantity"] = -3

    return {"sku_map": sku_map}

def correct_dataset(products_bad: list[dict], orders_bad: list[dict], sku_map: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Produces corrected versions of products/orders while preserving record IDs.
    """
    products_good = deepcopy(products_bad)
    orders_good = deepcopy(orders_bad)

    # Build SKU map dict
    sku_map_dict = {}
    for row in sku_map:
        old = str(row.get("old_sku", "")).strip()
        new = str(row.get("new_sku", "")).strip()
        if old and new:
            sku_map_dict[old.upper()] = new.upper()

    # 1) Fix whitespace SKUs in products (apply mapping if available, else normalize)
    for p in products_good:
        sku = str(p.get("sku", "")).strip()
        if not sku:
            continue
        key = sku.upper()
        if key in sku_map_dict:
            p["sku"] = sku_map_dict[key]
        else:
            # normalize spaces to dashes as a safe default
            p["sku"] = sku.replace(" ", "-").upper()

    # 2) Remove/resolve duplicate SKUs in products:
    # Keep the first occurrence; for any later duplicate SKU, make it unique by suffixing.
    seen = {}
    for p in products_good:
        sku = str(p.get("sku", "")).strip().upper()
        if not sku:
            continue
        if sku not in seen:
            seen[sku] = 1
        else:
            seen[sku] += 1
            p["sku"] = f"{sku}-DUP{seen[sku]}"

    # 3) Ensure name not blank
    for p in products_good:
        name = str(p.get("name", "")).strip()
        if not name:
            # Use SKU-based default name
            p["name"] = f"Unnamed {p.get('sku','PRODUCT')}".strip()

    # 4) Ensure UOM not blank
    for p in products_good:
        uom = str(p.get("uom", "")).strip()
        if not uom:
            p["uom"] = "ea"

    # 5) Ensure barcode uniqueness: if duplicates exist, append last 2 digits of product_id hash
    barcode_seen = {}
    for p in products_good:
        b = str(p.get("barcode", "")).strip()
        if not b:
            continue
        if b not in barcode_seen:
            barcode_seen[b] = 1
        else:
            barcode_seen[b] += 1
            suffix = abs(hash(str(p.get("product_id", "")))) % 100
            p["barcode"] = f"{b}{suffix:02d}"

    # Orders corrections
    # Apply sku mapping + normalization
    prod_skus = set(str(p.get("sku", "")).strip().upper() for p in products_good if str(p.get("sku","")).strip())
    for o in orders_good:
        raw = str(o.get("sku", "")).strip()
        if raw:
            mapped = sku_map_dict.get(raw.upper(), raw.upper())
            mapped = mapped.replace(" ", "-")
            o["sku"] = mapped

        # Fix invalid dates: if parsing fails, set to a valid fallback date
        od = str(o.get("order_date", "")).strip()
        try:
            datetime.strptime(od, "%Y-%m-%d")
        except Exception:
            o["order_date"] = "2025-01-01"

        # Fix quantity <= 0
        try:
            q = int(o.get("quantity", 0))
        except Exception:
            q = 0
        if q <= 0:
            o["quantity"] = 1

        # Fix unknown SKU: remap to a valid SKU deterministically
        sku = str(o.get("sku", "")).strip().upper()
        if sku and sku not in prod_skus:
            # map to a stable valid SKU using hash of order_row_id
            candidates = sorted(list(prod_skus))
            idx = abs(hash(str(o.get("order_row_id", "")))) % len(candidates)
            o["sku"] = candidates[idx]

    # Ensure sku_map entries are canonicalized (good file still includes mapping info)
    sku_map_good = []
    for row in sku_map:
        old = str(row.get("old_sku", "")).strip()
        new = str(row.get("new_sku", "")).strip()
        if old and new:
            sku_map_good.append({"old_sku": old.upper(), "new_sku": new.upper()})

    return products_good, orders_good, sku_map_good

def dump_yaml(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    print(f"Wrote: {path} ({path.stat().st_size/1024/1024:.2f} MB)")

def main():
    # Total requested: 10,000 records
    n_products = 1500
    n_orders = 8500

    products_base = make_products(n_products)
    product_skus_base = [p["sku"] for p in products_base]

    orders_base = make_orders(n_orders, product_skus_base)

    # BAD version
    products_bad = deepcopy(products_base)
    orders_bad = deepcopy(orders_base)
    extra = inject_issues(products_bad, orders_bad)
    sku_map_bad = extra["sku_map"]

    bad_payload = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "version": "demo-2",
            "quality": "bad",
            "counts": {"products": len(products_bad), "orders": len(orders_bad), "total": len(products_bad) + len(orders_bad)},
        },
        "products": products_bad,
        "orders": orders_bad,
        "sku_map": sku_map_bad,
    }

    # GOOD version (same records, corrected)
    products_good, orders_good, sku_map_good = correct_dataset(products_bad, orders_bad, sku_map_bad)

    good_payload = {
        "meta": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "version": "demo-2",
            "quality": "good",
            "counts": {"products": len(products_good), "orders": len(orders_good), "total": len(products_good) + len(orders_good)},
        },
        "products": products_good,
        "orders": orders_good,
        "sku_map": sku_map_good,
    }

    dump_yaml(Path("data/demo_10000_bad.yaml"), bad_payload)
    dump_yaml(Path("data/demo_10000_good.yaml"), good_payload)

if __name__ == "__main__":
    main()
