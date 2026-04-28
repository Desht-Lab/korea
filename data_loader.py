import pandas as pd
import numpy as np
from pathlib import Path
from database import init_db, bulk_upsert_companies, db_has_data

COLUMN_MAP = {
    "financial statement type": "financial_statement_type",
    "item code": "item_code",
    "company name": "company_name",
    "sector": "sector",
    "market category": "market_category",
    "industry": "industry",
    "industry name": "industry_name",
    "settlement date": "settlement_date",
    "current term revenue": "revenue_current",
    "previous term revenue": "revenue_previous",
    "term before previous revenue": "revenue_term_before",
    "current term revenue usd": "revenue_current_usd",
    "previous term revenue usd": "revenue_previous_usd",
    "term before previous revenue usd": "revenue_term_before_usd",
}


def _parse_numeric(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.strip()
        .replace(["nan", "None", "-", ""], np.nan)
        .astype(float, errors="ignore")
    )


def load_excel(path: str | Path) -> pd.DataFrame:
    df = pd.read_excel(path, engine="openpyxl")

    # Normalize column names
    df.columns = [c.strip().lower() for c in df.columns]
    rename = {}
    for col in df.columns:
        for key, val in COLUMN_MAP.items():
            if col == key:
                rename[col] = val
                break
    df = df.rename(columns=rename)

    # Parse numeric columns
    for col in ["revenue_current", "revenue_previous", "revenue_term_before",
                "revenue_current_usd", "revenue_previous_usd", "revenue_term_before_usd"]:
        if col in df.columns:
            df[col] = _parse_numeric(df[col])

    # Parse dates
    if "settlement_date" in df.columns:
        df["settlement_date"] = pd.to_datetime(df["settlement_date"], errors="coerce")

    # Deduplicate: keep latest settlement date per company
    if "settlement_date" in df.columns and "company_name" in df.columns:
        df = df.sort_values("settlement_date", ascending=False)
        df = df.drop_duplicates(subset="company_name", keep="first")

    # Compute revenue growth
    if "revenue_current_usd" in df.columns and "revenue_previous_usd" in df.columns:
        with np.errstate(divide="ignore", invalid="ignore"):
            df["revenue_growth"] = np.where(
                (df["revenue_previous_usd"].notna()) & (df["revenue_previous_usd"] != 0),
                (df["revenue_current_usd"] - df["revenue_previous_usd"]) / df["revenue_previous_usd"].abs() * 100,
                np.nan,
            )

    df = df.reset_index(drop=True)
    return df


def sync_to_db(df: pd.DataFrame, force: bool = False):
    init_db()
    if not force and db_has_data():
        return

    def _val(row, col, cast=None):
        v = row.get(col)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return cast(v) if cast else str(v)

    rows = []
    for _, row in df.iterrows():
        name = str(row.get("company_name", "")).strip()
        if not name:
            continue
        rows.append({
            "company_name": name,
            "sector": _val(row, "sector"),
            "industry": _val(row, "industry"),
            "industry_name": _val(row, "industry_name"),
            "market_category": _val(row, "market_category"),
            "revenue_current_usd": _val(row, "revenue_current_usd", float),
            "revenue_previous_usd": _val(row, "revenue_previous_usd", float),
            "revenue_term_before_usd": _val(row, "revenue_term_before_usd", float),
            "revenue_growth": _val(row, "revenue_growth", float),
            "settlement_date": row["settlement_date"].isoformat() if pd.notna(row.get("settlement_date")) else None,
        })

    if rows:
        bulk_upsert_companies(rows)
