from typing import Dict, List
import pandas as pd
from .base import Finding

ALLOWED_STATUS = {"active", "inactive", "discontinued"}

def _is_blank(s: str) -> bool:
    return str(s).strip() == "" or str(s).strip().lower() == "none"

def _to_float(x: str):
    try:
        return float(str(x).strip())
    except Exception:
        return None

def audit_products(df: pd.DataFrame, all_tables: Dict[str, pd.DataFrame]) -> List[Finding]:
    f: List[Finding] = []

    # SKU blank + whitespace warnings
    if "sku" in df.columns:
        sku = df["sku"].astype(str)

        blank = sku.str.strip().eq("")
        for idx in df[blank].index.tolist():
            f.append(Finding(
                entity="products", severity="ERROR", code="SKU_BLANK",
                message="SKU is blank.",
                row=int(idx), field="sku",
                fix="Set a non-empty unique SKU. Keep SKU stable across systems/channels."
            ))

        has_ws = sku.str.contains(r"\s", regex=True)
        for idx in df[has_ws].index.tolist():
            f.append(Finding(
                entity="products", severity="WARN", code="SKU_HAS_WHITESPACE",
                message="SKU contains whitespace; can break channel mapping/integrations and matching.",
                row=int(idx), field="sku", value=str(df.loc[idx, "sku"]),
                fix="Replace spaces with '-' or '_' (e.g., 'SKU 1004' → 'SKU-1004') and update references."
            ))

        # SKU normalization collision check (case/trim)
        normalized = sku.str.strip().str.upper()
        # collision means: normalized duplicates BUT raw values are not identical
        dup_norm = normalized.duplicated(keep=False) & (~normalized.eq(""))
        for idx in df[dup_norm].index.tolist():
            # check if at least one other row has same normalized but different raw
            raw_val = str(df.loc[idx, "sku"])
            same_norm = df[normalized == normalized.loc[idx]]["sku"].astype(str).tolist()
            if any(v != raw_val for v in same_norm):
                f.append(Finding(
                    entity="products", severity="ERROR", code="SKU_NORMALIZATION_COLLISION",
                    message="Two SKUs become identical after normalization (trim/upper).",
                    row=int(idx), field="sku", value=raw_val,
                    fix="Make SKUs distinct even after trimming and case normalization."
                ))


    # Name required
    if "name" in df.columns:
        blank_name = df["name"].astype(str).str.strip().eq("")
        for idx in df[blank_name].index.tolist():
            f.append(Finding(
                entity="products", severity="ERROR", code="NAME_BLANK",
                message="Product name is blank.",
                row=int(idx), field="name",
                fix="Set a product name; it's required for selling, picking docs, and reporting."
            ))

    # UOM required (warn or error depending on your policy)
    if "uom" in df.columns:
        blank_uom = df["uom"].astype(str).str.strip().eq("")
        for idx in df[blank_uom].index.tolist():
            f.append(Finding(
                entity="products", severity="WARN", code="UOM_BLANK",
                message="UOM is blank; can break purchasing/receiving and pack/pick logic.",
                row=int(idx), field="uom", value=str(df.loc[idx, "uom"]),
                fix="Set a UOM like 'ea', 'case', 'box'. Keep consistent across all imports."
            ))

    # Status enum
    if "status" in df.columns:
        bad = ~df["status"].astype(str).str.lower().isin(ALLOWED_STATUS)
        for idx in df[bad].index.tolist():
            f.append(Finding(
                entity="products", severity="WARN", code="STATUS_UNEXPECTED",
                message="Status value is not in the recommended set.",
                row=int(idx), field="status", value=str(df.loc[idx, "status"]),
                fix=f"Use one of: {sorted(ALLOWED_STATUS)} (or align to your Fulfil config)."
            ))

    # Numeric checks: cost/price
    for col in ["cost", "price"]:
        if col in df.columns:
            for idx in df.index.tolist():
                v = _to_float(df.loc[idx, col])
                if v is None:
                    f.append(Finding(
                        entity="products", severity="ERROR", code=f"{col.upper()}_NOT_NUMERIC",
                        message=f"{col} must be numeric.",
                        row=int(idx), field=col, value=str(df.loc[idx, col]),
                        fix=f"Provide a numeric {col} (e.g., 6.50)."
                    ))
                elif v < 0:
                    f.append(Finding(
                        entity="products", severity="ERROR", code=f"{col.upper()}_NEGATIVE",
                        message=f"{col} cannot be negative.",
                        row=int(idx), field=col, value=str(df.loc[idx, col]),
                        fix=f"Set {col} to 0 or a positive number."
                    ))

    # Barcode uniqueness (common issue)
    if "barcode" in df.columns:
        b = df["barcode"].astype(str).str.strip()
        dup_b = b.duplicated(keep=False) & (~b.eq(""))
        for idx in df[dup_b].index.tolist():
            f.append(Finding(
                entity="products", severity="WARN", code="BARCODE_DUPLICATE",
                message="Barcode is duplicated across products; can break scanning/picking.",
                row=int(idx), field="barcode", value=str(df.loc[idx, "barcode"]),
                fix="Ensure barcode/UPC is unique per sellable item/variant."
            ))

    return f
