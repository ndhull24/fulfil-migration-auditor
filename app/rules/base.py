from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
import pandas as pd

@dataclass
class Finding:
    entity: str
    severity: str  # "ERROR" | "WARN" | "SUGGEST"
    code: str
    message: str
    row: Optional[int] = None
    field: Optional[str] = None
    value: Optional[str] = None
    fix: Optional[str] = None

RuleFn = Callable[[pd.DataFrame, Dict[str, pd.DataFrame]], List[Finding]]

@dataclass
class Rule:
    entity: str
    code: str
    description: str
    fn: RuleFn
