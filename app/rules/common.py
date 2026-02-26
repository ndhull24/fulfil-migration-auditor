from typing import Dict, List
import pandas as pd
from .base import Finding

def require_columns(entity: str, df: pd.DataFrame, cols: List[str]) -> List[Finding]:
    findings: List[Finding] = []
    for c in cols:
        if c not in df.columns:
            findings.append(Finding(
                entity=entity, severity="ERROR", code="MISSING_COLUMN",
                message=f"Missing required column: {c}",
                fix=f"Add column '{c}' to the file (even if blank) and re-run."
            ))
    return findings

def unique_key(entity: str, df: pd.DataFrame, key: str) -> List[Finding]:
    findings: List[Finding] = []
    if key not in df.columns:
        return findings
    dupes = df[df[key].astype(str).str.strip().eq("") == False].duplicated(subset=[key], keep=False)
    for idx in df[dupes].index.tolist():
        findings.append(Finding(
            entity=entity, severity="ERROR", code="DUPLICATE_KEY",
            message=f"Duplicate {key} detected.",
            row=int(idx), field=key, value=str(df.loc[idx, key]),
            fix=f"Ensure '{key}' is unique for every record."
        ))
    return findings
