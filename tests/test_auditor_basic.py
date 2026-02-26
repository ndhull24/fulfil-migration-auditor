import pandas as pd
from app.rules.common import unique_key
from app.rules.products import audit_products
from app.reconcile.cross_checks import orders_reference_existing_skus
from app.reconcile.sku_map import load_sku_map

def test_duplicate_sku_detected():
    df = pd.DataFrame({
        "sku": ["SKU-1", "SKU-1"],
        "name": ["A", "B"]
    })
    findings = unique_key("products", df, "sku")
    assert any(f.code == "DUPLICATE_KEY" for f in findings)

def test_order_sku_not_found():
    products = pd.DataFrame({"sku": ["SKU-1"], "name": ["A"], "uom": ["ea"], "status": ["active"], "cost": ["1"], "price": ["2"]})
    orders = pd.DataFrame({"order_id": ["O1"], "order_date": ["2025-01-01"], "channel": ["Shopify"], "customer_id": ["C1"], "sku": ["SKU-999"], "quantity": ["1"], "warehouse": ["WH-1"], "status": ["open"]})
    tables = {"products": products, "orders": orders}
    findings = orders_reference_existing_skus(tables, sku_map={})
    assert any(f.code == "SKU_NOT_FOUND" for f in findings)

def test_sku_mapping_removes_not_found():
    products = pd.DataFrame({"sku": ["SKU-1004"], "name": ["Hoodie"], "uom": ["ea"], "status": ["active"], "cost": ["1"], "price": ["2"]})
    orders = pd.DataFrame({"order_id": ["O1"], "order_date": ["2025-01-01"], "channel": ["Shopify"], "customer_id": ["C1"], "sku": ["SKU 1004"], "quantity": ["1"], "warehouse": ["WH-1"], "status": ["open"]})
    tables = {"products": products, "orders": orders}
    sku_map = {"SKU 1004".strip().upper(): "SKU-1004"}
    findings = orders_reference_existing_skus(tables, sku_map=sku_map)
    assert not any(f.code == "SKU_NOT_FOUND" for f in findings)
    assert any(f.code == "SKU_MAPPED" for f in findings)
