from typing import Dict, List
import pandas as pd
from .base import Finding

ALLOWED_CHANNELS = {"shopify", "amazon", "wholesale"}
ALLOWED_STATUS = {"open", "paid", "fulfilled", "cancelled", "closed"}

def _to_int(x: str):
    try:
        return int(float(str(x).strip()))
    except Exception:
        return None

def audit_orders(df: pd.DataFrame, all_tables: Dict[str, pd.DataFrame]) -> List[Finding]:
    f: List[Finding] = []

    # order_id required and unique
    if "order_id" in df.columns:
        blank = df["order_id"].astype(str).str.strip().eq("")
        for idx in df[blank].index.tolist():
            f.append(Finding(
                entity="orders", severity="ERROR", code="ORDER_ID_BLANK",
                message="order_id is blank.",
                row=int(idx), field="order_id",
                fix="Every order must have a unique order_id."
            ))
        dup = df["order_id"].astype(str).str.strip().duplicated(keep=False)
        for idx in df[dup].index.tolist():
            f.append(Finding(
                entity="orders", severity="ERROR", code="ORDER_ID_DUPLICATE",
                message="Duplicate order_id detected.",
                row=int(idx), field="order_id", value=str(df.loc[idx, "order_id"]),
                fix="Make order_id unique."
            ))

    # order_date parseable
    if "order_date" in df.columns:
        parsed = pd.to_datetime(df["order_date"], errors="coerce")
        bad = parsed.isna()
        for idx in df[bad].index.tolist():
            f.append(Finding(
                entity="orders", severity="ERROR", code="ORDER_DATE_INVALID",
                message="order_date is not a valid date.",
                row=int(idx), field="order_date", value=str(df.loc[idx, "order_date"]),
                fix="Use ISO format like YYYY-MM-DD."
            ))

    # quantity integer > 0
    if "quantity" in df.columns:
        for idx in df.index.tolist():
            q = _to_int(df.loc[idx, "quantity"])
            if q is None:
                f.append(Finding(
                    entity="orders", severity="ERROR", code="QTY_NOT_INTEGER",
                    message="quantity must be an integer.",
                    row=int(idx), field="quantity", value=str(df.loc[idx, "quantity"]),
                    fix="Use whole numbers (e.g., 1, 2, 5)."
                ))
            elif q <= 0:
                f.append(Finding(
                    entity="orders", severity="ERROR", code="QTY_NON_POSITIVE",
                    message="quantity must be > 0.",
                    row=int(idx), field="quantity", value=str(df.loc[idx, "quantity"]),
                    fix="Set quantity to a positive integer."
                ))

    # channel enum
    if "channel" in df.columns:
        ch = df["channel"].astype(str).str.lower().str.strip()
        bad = ~ch.isin(ALLOWED_CHANNELS)
        for idx in df[bad].index.tolist():
            f.append(Finding(
                entity="orders", severity="WARN", code="CHANNEL_UNEXPECTED",
                message="channel is not in the recommended set.",
                row=int(idx), field="channel", value=str(df.loc[idx, "channel"]),
                fix=f"Use one of: {sorted(ALLOWED_CHANNELS)} (or extend the allowed set)."
            ))

    # status enum
    if "status" in df.columns:
        st = df["status"].astype(str).str.lower().str.strip()
        bad = ~st.isin(ALLOWED_STATUS)
        for idx in df[bad].index.tolist():
            f.append(Finding(
                entity="orders", severity="WARN", code="ORDER_STATUS_UNEXPECTED",
                message="status is not in the recommended set.",
                row=int(idx), field="status", value=str(df.loc[idx, "status"]),
                fix=f"Use one of: {sorted(ALLOWED_STATUS)} (or align to your lifecycle)."
            ))

    # SKU whitespace warning (order-side)
    if "sku" in df.columns:
        sku = df["sku"].astype(str)
        has_ws = sku.str.contains(r"\s", regex=True)
        for idx in df[has_ws].index.tolist():
            f.append(Finding(
                entity="orders", severity="WARN", code="ORDER_SKU_HAS_WHITESPACE",
                message="Order SKU contains whitespace; may not match product master in integrations.",
                row=int(idx), field="sku", value=str(df.loc[idx, "sku"]),
                fix="Normalize SKUs (replace spaces with '-' or '_') and keep consistent across files."
            ))

    return f
