import sqlite3
import json
import pandas as pd
from pathlib import Path

DB_PATH = Path(__file__).parent / "radar.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS companies_enriched (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT UNIQUE NOT NULL,
            sector TEXT,
            industry TEXT,
            industry_name TEXT,
            market_category TEXT,
            revenue_current_usd REAL,
            revenue_previous_usd REAL,
            revenue_term_before_usd REAL,
            revenue_growth REAL,
            settlement_date TEXT,
            headquarters_location TEXT,
            production_locations TEXT,
            business_description TEXT,
            main_products TEXT,
            central_asia_presence TEXT,
            kazakhstan_presence TEXT,
            uzbekistan_presence TEXT,
            azerbaijan_presence TEXT,
            georgia_presence TEXT,
            armenia_presence TEXT,
            kyrgyzstan_presence TEXT,
            source_links TEXT,
            likelihood_kz TEXT,
            likelihood_reasoning TEXT,
            why_kazakhstan TEXT,
            engagement_format TEXT,
            negotiation_questions TEXT,
            last_updated TEXT,
            research_status TEXT DEFAULT 'not_researched'
        )
    """)
    conn.commit()
    conn.close()


def db_has_data() -> bool:
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM companies_enriched").fetchone()[0]
    conn.close()
    return count > 0


def bulk_upsert_companies(rows: list[dict]):
    sql = """
        INSERT INTO companies_enriched
            (company_name, sector, industry, industry_name, market_category,
             revenue_current_usd, revenue_previous_usd, revenue_term_before_usd,
             revenue_growth, settlement_date)
        VALUES
            (:company_name, :sector, :industry, :industry_name, :market_category,
             :revenue_current_usd, :revenue_previous_usd, :revenue_term_before_usd,
             :revenue_growth, :settlement_date)
        ON CONFLICT(company_name) DO UPDATE SET
            sector=excluded.sector,
            industry=excluded.industry,
            industry_name=excluded.industry_name,
            market_category=excluded.market_category,
            revenue_current_usd=excluded.revenue_current_usd,
            revenue_previous_usd=excluded.revenue_previous_usd,
            revenue_term_before_usd=excluded.revenue_term_before_usd,
            revenue_growth=excluded.revenue_growth,
            settlement_date=excluded.settlement_date
    """
    conn = get_connection()
    conn.executemany(sql, rows)
    conn.commit()
    conn.close()


def save_research(company_name: str, research: dict):
    import datetime

    def _serialize(val):
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False)
        return val

    conn = get_connection()
    conn.execute("""
        UPDATE companies_enriched SET
            headquarters_location = :headquarters_location,
            production_locations = :production_locations,
            business_description = :business_description,
            main_products = :main_products,
            central_asia_presence = :central_asia_presence,
            kazakhstan_presence = :kazakhstan_presence,
            uzbekistan_presence = :uzbekistan_presence,
            azerbaijan_presence = :azerbaijan_presence,
            georgia_presence = :georgia_presence,
            armenia_presence = :armenia_presence,
            kyrgyzstan_presence = :kyrgyzstan_presence,
            source_links = :source_links,
            likelihood_kz = :likelihood_kz,
            likelihood_reasoning = :likelihood_reasoning,
            why_kazakhstan = :why_kazakhstan,
            engagement_format = :engagement_format,
            negotiation_questions = :negotiation_questions,
            last_updated = :last_updated,
            research_status = 'researched'
        WHERE company_name = :company_name
    """, {
        "company_name": company_name,
        "last_updated": datetime.datetime.utcnow().isoformat(),
        "headquarters_location": _serialize(research.get("headquarters_location")),
        "production_locations": _serialize(research.get("production_table")),
        "business_description": _serialize(research.get("business_description")),
        "main_products": _serialize(research.get("main_products")),
        "central_asia_presence": _serialize(research.get("central_asia_presence")),
        "kazakhstan_presence": _serialize(research.get("kazakhstan_presence")),
        "uzbekistan_presence": _serialize(research.get("uzbekistan_presence")),
        "azerbaijan_presence": _serialize(research.get("azerbaijan_presence")),
        "georgia_presence": _serialize(research.get("georgia_presence")),
        "armenia_presence": _serialize(research.get("armenia_presence")),
        "kyrgyzstan_presence": _serialize(research.get("kyrgyzstan_presence")),
        "source_links": json.dumps(research.get("source_links", []), ensure_ascii=False),
        "likelihood_kz": _serialize(research.get("likelihood_kz")),
        "likelihood_reasoning": _serialize(research.get("likelihood_reasoning")),
        "why_kazakhstan": _serialize(research.get("why_kazakhstan")),
        "engagement_format": _serialize(research.get("engagement_format")),
        "negotiation_questions": _serialize(research.get("negotiation_questions")),
    })
    conn.commit()
    conn.close()


def get_all_companies() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM companies_enriched ORDER BY revenue_current_usd DESC NULLS LAST", conn)
    conn.close()
    return df


def get_company(name: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM companies_enriched WHERE company_name = ?", (name,)
    ).fetchone()
    conn.close()
    if row:
        d = dict(row)
        if d.get("source_links"):
            try:
                d["source_links"] = json.loads(d["source_links"])
            except Exception:
                d["source_links"] = []
        return d
    return None
