from pathlib import Path
import pandas as pd

def load_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(str(path))

    if path.suffix.lower() in [".csv"]:
        return pd.read_csv(path, dtype=str).fillna("")
    if path.suffix.lower() in [".xlsx", ".xls"]:
        return pd.read_excel(path, dtype=str).fillna("")
    raise ValueError(f"Unsupported file type: {path.suffix}")
