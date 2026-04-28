import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from sector_map import SECTOR_MAP
from data_loader import load_excel, sync_to_db
from database import init_db, get_all_companies, get_company, save_research

# ─── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Korea–Kazakhstan Opportunity Radar",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .main { background-color: #ffffff; }

    .kpi-card {
        background: #ffffff;
        border: 1px solid #e8edf2;
        border-left: 4px solid #376c8a;
        border-radius: 6px;
        padding: 16px 20px;
        margin-bottom: 8px;
    }
    .kpi-label {
        font-size: 12px;
        font-weight: 500;
        color: #7a8fa0;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 4px;
    }
    .kpi-value {
        font-size: 26px;
        font-weight: 700;
        color: #1a2e3b;
    }
    .kpi-sub {
        font-size: 12px;
        color: #7a8fa0;
        margin-top: 2px;
    }

    .section-header {
        font-size: 11px;
        font-weight: 600;
        color: #376c8a;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin: 24px 0 8px 0;
        padding-bottom: 6px;
        border-bottom: 1px solid #e8edf2;
    }

    .badge-high { background:#d4edda; color:#155724; padding:2px 8px; border-radius:12px; font-size:12px; font-weight:600; }
    .badge-medium { background:#fff3cd; color:#856404; padding:2px 8px; border-radius:12px; font-size:12px; font-weight:600; }
    .badge-low { background:#f8d7da; color:#721c24; padding:2px 8px; border-radius:12px; font-size:12px; font-weight:600; }
    .badge-researched { background:#cce5ff; color:#004085; padding:2px 8px; border-radius:12px; font-size:12px; }
    .badge-not { background:#f2f2f2; color:#6c757d; padding:2px 8px; border-radius:12px; font-size:12px; }

    .briefing-block {
        background: #f8fafb;
        border: 1px solid #e8edf2;
        border-radius: 6px;
        padding: 16px 20px;
        margin-bottom: 12px;
    }

    .source-link {
        font-size: 12px;
        color: #376c8a;
        word-break: break-all;
    }

    div[data-testid="stSidebar"] {
        background: #1a2e3b;
    }
    div[data-testid="stSidebar"] * {
        color: #c8d8e4 !important;
    }
    div[data-testid="stSidebar"] .stSelectbox label,
    div[data-testid="stSidebar"] .stMultiSelect label,
    div[data-testid="stSidebar"] .stSlider label {
        color: #c8d8e4 !important;
        font-size: 12px !important;
    }

    h1 { font-size: 22px !important; font-weight: 700 !important; color: #1a2e3b !important; }
    h2 { font-size: 17px !important; font-weight: 600 !important; color: #1a2e3b !important; }
    h3 { font-size: 14px !important; font-weight: 600 !important; color: #376c8a !important; }
</style>
""", unsafe_allow_html=True)

ACCENT = "#376c8a"

# ─── State ───────────────────────────────────────────────────────────────────
if "page" not in st.session_state:
    st.session_state.page = "dashboard"
if "selected_company" not in st.session_state:
    st.session_state.selected_company = None

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _fmt_num(val: float) -> str:
    """Format number as 1 000.00 with space as thousands separator."""
    formatted = f"{abs(val):,.2f}".replace(",", " ")  # thin space
    return f"-{formatted}" if val < 0 else formatted


def fmt_usd(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    return f"$ {_fmt_num(val / 1e6)} млн"


def fmt_pct(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    sign = "+" if val > 0 else ""
    return f"{sign}{_fmt_num(val)} %"


def badge(val):
    if val == "High":
        return '<span class="badge-high">High</span>'
    elif val == "Medium":
        return '<span class="badge-medium">Medium</span>'
    elif val == "Low":
        return '<span class="badge-low">Low</span>'
    return "—"


def sector_label(code):
    if not code:
        return code
    return f"{code} — {SECTOR_MAP.get(str(code), code)}"


@st.cache_data(show_spinner=False)
def load_data_cached(path):
    return load_excel(path)


def ensure_data():
    from database import db_has_data
    if db_has_data():
        return True
    default_path = Path(__file__).parent / "companies.xlsx"
    if default_path.exists():
        with st.spinner("Первичная загрузка данных..."):
            df = load_data_cached(str(default_path))
            sync_to_db(df)
    return True


# ─── Sidebar ─────────────────────────────────────────────────────────────────

def sidebar():
    with st.sidebar:
        st.markdown("## 🇰🇷 → 🇰🇿")
        st.markdown("**Korea–Kazakhstan**  \nOpportunity Radar")
        st.markdown("---")

        if st.button("📊 Дашборд", use_container_width=True):
            st.session_state.page = "dashboard"
            st.rerun()
        if st.button("🏢 Список компаний", use_container_width=True):
            st.session_state.page = "companies"
            st.rerun()

        st.markdown("---")
        api_key = st.text_input("Google API Key", type="password",
                                 value=os.getenv("GOOGLE_API_KEY", ""),
                                 help="Для AI-исследования (Gemini 2.5 Flash-Lite)")
        if api_key:
            os.environ["GOOGLE_API_KEY"] = api_key


# ─── DASHBOARD ───────────────────────────────────────────────────────────────

def page_dashboard():
    ensure_data()
    db_df = get_all_companies()

    st.markdown("# Korea–Kazakhstan Company Opportunity Radar")
    st.markdown("*Анализ корейских компаний для поиска инвестиционных и партнёрских возможностей*")

    if db_df.empty:
        st.info("Загрузите файл companies.xlsx через боковую панель.")
        return

    # ── Filters ──────────────────────────────────────────────────────────────
    with st.expander("🔧 Фильтры", expanded=False):
        col1, col2 = st.columns(2)
        sectors = sorted(db_df["sector"].dropna().unique())
        sel_sector = col1.multiselect("Сектор", sectors,
                                      format_func=lambda x: sector_label(x))
        cats = sorted(db_df["market_category"].dropna().unique())
        sel_cat = col2.multiselect("Market Category", cats)

        rev_max = float(db_df["revenue_current_usd"].max(skipna=True) or 1e9)
        rev_range = st.slider("Выручка USD (диапазон)",
                               0.0, rev_max, (0.0, rev_max),
                               format="%.0f")

    fdf = db_df.copy()
    if sel_sector:
        fdf = fdf[fdf["sector"].isin(sel_sector)]
    if sel_cat:
        fdf = fdf[fdf["market_category"].isin(sel_cat)]
    fdf = fdf[
        (fdf["revenue_current_usd"].fillna(0) >= rev_range[0]) &
        (fdf["revenue_current_usd"].fillna(0) <= rev_range[1])
    ]

    # ── KPIs ─────────────────────────────────────────────────────────────────
    total = len(fdf)
    total_rev = fdf["revenue_current_usd"].sum(skipna=True)
    avg_rev = fdf["revenue_current_usd"].mean(skipna=True)
    researched = (fdf["research_status"] == "researched").sum()
    high_kz = (fdf["likelihood_kz"] == "High").sum()

    c1, c2, c3, c4, c5 = st.columns(5)
    for col, label, val, sub in [
        (c1, "Компаний", f"{total:,}", "уникальных"),
        (c2, "Суммарная выручка", fmt_usd(total_rev), "последний период"),
        (c3, "Средняя выручка", fmt_usd(avg_rev), "на компанию"),
        (c4, "Исследовано AI", f"{researched}", f"из {total}"),
        (c5, "Высокий приоритет КЗ", f"{high_kz}", "компаний"),
    ]:
        col.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{val}</div>
            <div class="kpi-sub">{sub}</div>
        </div>""", unsafe_allow_html=True)

    # ── Charts ───────────────────────────────────────────────────────────────
    st.markdown('<div class="section-header">Аналитика</div>', unsafe_allow_html=True)

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        # Companies by sector
        sec_cnt = fdf["sector"].value_counts().head(20).sort_values(ascending=True).reset_index()
        sec_cnt.columns = ["sector", "count"]
        sec_cnt["label"] = sec_cnt["sector"].apply(sector_label)
        fig = px.bar(sec_cnt, x="count", y="label", orientation="h",
                     title="Компании по секторам",
                     color_discrete_sequence=[ACCENT])
        fig.update_layout(height=520, yaxis_title="", xaxis_title="Компаний",
                          plot_bgcolor="white", paper_bgcolor="white",
                          title_font_size=13, margin=dict(l=0, r=10, t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)

    with chart_col2:
        # Industry bar
        ind_cnt = fdf["industry_name"].value_counts().head(15).sort_values(ascending=True).reset_index()
        ind_cnt.columns = ["industry_name", "count"]
        fig3 = px.bar(ind_cnt, x="count", y="industry_name", orientation="h",
                      title="Компании по отраслям (топ-15)",
                      color_discrete_sequence=["#5a9ab5"])
        fig3.update_layout(height=520, yaxis_title="", xaxis_title="Компаний",
                           plot_bgcolor="white", paper_bgcolor="white",
                           title_font_size=13, margin=dict(l=0, r=10, t=40, b=20))
        st.plotly_chart(fig3, use_container_width=True)

    # ── Top 10 ───────────────────────────────────────────────────────────────
    st.markdown('<div class="section-header">Топ-10 компаний по выручке</div>', unsafe_allow_html=True)
    top10 = fdf.nlargest(10, "revenue_current_usd")[
        ["company_name", "sector", "industry_name", "revenue_current_usd", "revenue_growth", "likelihood_kz"]
    ].copy()
    top10["Выручка USD"] = top10["revenue_current_usd"].apply(fmt_usd)
    top10["Рост %"] = top10["revenue_growth"].apply(lambda x: fmt_pct(x) if pd.notna(x) else "—")
    top10["Сектор"] = top10["sector"].apply(lambda x: sector_label(x) if x else "—")
    top10 = top10.rename(columns={
        "company_name": "Компания", "industry_name": "Отрасль",
        "likelihood_kz": "КЗ приоритет"
    })
    st.dataframe(
        top10[["Компания", "Сектор", "Отрасль", "Выручка USD", "Рост %", "КЗ приоритет"]],
        use_container_width=True, hide_index=True
    )


# ─── COMPANY LIST ─────────────────────────────────────────────────────────────

def page_companies():
    ensure_data()
    db_df = get_all_companies()

    st.markdown("# Список компаний")

    if db_df.empty:
        st.info("Данные не загружены.")
        return

    # Search & filters
    col_s, col_f1, col_f2, col_f3 = st.columns([3, 1, 1, 1])
    search = col_s.text_input("🔍 Поиск по названию", "")
    sel_sec = col_f1.selectbox("Сектор", ["Все"] + sorted(db_df["sector"].dropna().unique().tolist()))
    sel_cat = col_f2.selectbox("Market Cat", ["Все"] + sorted(db_df["market_category"].dropna().unique().tolist()))
    sel_lk = col_f3.selectbox("КЗ приоритет", ["Все", "High", "Medium", "Low"])

    fdf = db_df.copy()
    if search:
        fdf = fdf[fdf["company_name"].str.contains(search, case=False, na=False)]
    if sel_sec != "Все":
        fdf = fdf[fdf["sector"] == sel_sec]
    if sel_cat != "Все":
        fdf = fdf[fdf["market_category"] == sel_cat]
    if sel_lk != "Все":
        fdf = fdf[fdf["likelihood_kz"] == sel_lk]

    # Sort
    sort_col = st.selectbox("Сортировать по", ["revenue_current_usd", "revenue_growth", "company_name"],
                            format_func=lambda x: {"revenue_current_usd": "Выручка USD",
                                                    "revenue_growth": "Рост %",
                                                    "company_name": "Название"}[x])
    fdf = fdf.sort_values(sort_col, ascending=sort_col == "company_name", na_position="last")

    st.markdown(f"**{len(fdf):,}** компаний")

    # Bulk research
    if os.getenv("GOOGLE_API_KEY"):
        sel_names = st.multiselect("Выбрать для AI-исследования",
                                    fdf["company_name"].tolist())
        if sel_names and st.button(f"🤖 Исследовать выбранные ({len(sel_names)})", type="primary"):
            _run_bulk_research(sel_names)

    # Table
    display = fdf[["company_name", "sector", "industry_name", "market_category",
                   "revenue_current_usd", "revenue_growth",
                   "research_status", "likelihood_kz"]].copy()
    display["Выручка USD"] = display["revenue_current_usd"].apply(fmt_usd)
    display["Рост %"] = display["revenue_growth"].apply(lambda x: fmt_pct(x) if pd.notna(x) else "—")
    display["Сектор"] = display["sector"].apply(lambda x: sector_label(x) if x else "—")
    display = display.rename(columns={
        "company_name": "Компания", "industry_name": "Отрасль",
        "market_category": "Кат.", "research_status": "AI статус",
        "likelihood_kz": "КЗ"
    })

    st.dataframe(
        display[["Компания", "Сектор", "Отрасль", "Кат.", "Выручка USD", "Рост %", "AI статус", "КЗ"]],
        use_container_width=True, hide_index=True
    )

    st.markdown("---")
    st.markdown("**Открыть карточку компании:**")
    chosen = st.selectbox("Выбрать компанию", [""] + fdf["company_name"].tolist(),
                          format_func=lambda x: x or "— выберите —")
    if chosen:
        st.session_state.selected_company = chosen
        st.session_state.page = "detail"
        st.rerun()


def _run_bulk_research(names):
    from ai_research import make_client, research_company
    client = make_client(os.environ["GOOGLE_API_KEY"])
    prog = st.progress(0)
    for i, name in enumerate(names):
        st.toast(f"Исследую: {name}")
        row = get_company(name)
        result = research_company(
            name,
            row.get("sector") if row else None,
            row.get("industry_name") if row else None,
            client
        )
        save_research(name, result)
        prog.progress((i + 1) / len(names))
    prog.empty()
    st.success("Исследование завершено!")
    st.rerun()


# ─── COMPANY DETAIL ──────────────────────────────────────────────────────────

def page_detail():
    name = st.session_state.selected_company
    if not name:
        st.warning("Компания не выбрана.")
        return

    row = get_company(name)
    if not row:
        st.error("Компания не найдена в базе данных.")
        return

    # Header
    if st.button("← Назад к списку"):
        st.session_state.page = "companies"
        st.rerun()

    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        st.markdown(f"# {name}")
        st.markdown(f"*{sector_label(row.get('sector'))} · {row.get('industry_name', '—')} · {row.get('market_category', '—')}*")
    with col_h2:
        lk = row.get("likelihood_kz")
        if lk:
            st.markdown(f"**Приоритет КЗ:**")
            st.markdown(badge(lk), unsafe_allow_html=True)

    st.markdown("---")

    # ── A. Financial data ─────────────────────────────────────────────────
    st.markdown('<div class="section-header">A. Финансовые показатели</div>', unsafe_allow_html=True)
    fc1, fc2, fc3 = st.columns(3)
    for col, label, val in [
        (fc1, "Текущий период", fmt_usd(row.get("revenue_current_usd"))),
        (fc2, "Предыдущий период", fmt_usd(row.get("revenue_previous_usd"))),
        (fc3, "Период до предыдущего", fmt_usd(row.get("revenue_term_before_usd"))),
    ]:
        col.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{val}</div>
        </div>""", unsafe_allow_html=True)

    grow = row.get("revenue_growth")
    if grow is not None:
        arrow = "▲" if grow > 0 else ("▼" if grow < 0 else "—")
        color = "#28a745" if grow > 0 else ("#dc3545" if grow < 0 else "#6c757d")
        st.markdown(f"**Рост:** <span style='color:{color};font-size:16px'>{arrow} {fmt_pct(grow)}</span>",
                    unsafe_allow_html=True)

    # AI Research
    is_researched = row.get("research_status") == "researched"

    if not is_researched:
        st.markdown('<div class="section-header">B. AI Исследование</div>', unsafe_allow_html=True)
        if os.getenv("GOOGLE_API_KEY"):
            if st.button("🤖 Запустить AI исследование", type="primary"):
                _run_single_research(row)
        else:
            st.info("Введите Google API ключ в боковой панели для запуска исследования.")
        return

    # ── B. AI Research block ───────────────────────────────────────────────
    st.markdown('<div class="section-header">B. Обзор компании</div>', unsafe_allow_html=True)

    st.markdown(f"""
    <div class="briefing-block">
        <div class="kpi-label">Чем занимается</div>
        <p style="margin:6px 0 0 0">{row.get('business_description', '—')}</p>
    </div>
    <div class="briefing-block">
        <div class="kpi-label">Основные продукты / услуги</div>
        <p style="margin:6px 0 0 0">{row.get('main_products', '—')}</p>
    </div>
    <div class="briefing-block">
        <div class="kpi-label">Штаб-квартира</div>
        <p style="margin:6px 0 0 0">{row.get('headquarters_location', '—')}</p>
    </div>
    <div class="briefing-block">
        <div class="kpi-label">Производственные мощности</div>
        <p style="margin:6px 0 0 0">{row.get('production_locations', '—')}</p>
    </div>
    """, unsafe_allow_html=True)

    # ── Regional presence ─────────────────────────────────────────────────
    st.markdown('<div class="section-header">C. Присутствие в регионе</div>', unsafe_allow_html=True)

    kz = row.get("kazakhstan_presence")
    if isinstance(kz, str):
        try:
            kz = json.loads(kz)
        except Exception:
            kz = {"details": kz}

    with st.expander("🇰🇿 Казахстан", expanded=True):
        if isinstance(kz, dict):
            exists = kz.get("exists", False)
            st.markdown(f"**Наличие:** {'✅ Есть' if exists else '❌ Не подтверждено'}")
            st.markdown(f"**Проекты:** {kz.get('projects', '—')}")
            st.markdown(f"**Партнёры:** {kz.get('partners', '—')}")
            if kz.get("details") and kz["details"] != kz.get("projects"):
                st.markdown(f"**Детали:** {kz['details']}")
        else:
            st.markdown(row.get("kazakhstan_presence", "—"))

    countries = [
        ("🇺🇿 Узбекистан", "uzbekistan_presence"),
        ("🇦🇿 Азербайджан", "azerbaijan_presence"),
        ("🇬🇪 Грузия", "georgia_presence"),
        ("🇦🇲 Армения", "armenia_presence"),
        ("🇰🇬 Кыргызстан", "kyrgyzstan_presence"),
    ]
    for label, field in countries:
        val = row.get(field, "—") or "Не подтверждено"
        with st.expander(label):
            st.write(val)

    # ── D. KZ Opportunity Scoring ─────────────────────────────────────────
    st.markdown('<div class="section-header">D. Оценка выхода в Казахстан</div>', unsafe_allow_html=True)

    lk_val = row.get("likelihood_kz", "—")
    lk_color = {"High": "#28a745", "Medium": "#ffc107", "Low": "#dc3545"}.get(lk_val, "#6c757d")
    st.markdown(f"""
    <div class="briefing-block">
        <div class="kpi-label">Вероятность</div>
        <span style="font-size:20px; font-weight:700; color:{lk_color}">{lk_val}</span>
        <p style="margin:8px 0 0 0; color:#444">{row.get('likelihood_reasoning', '—')}</p>
    </div>
    """, unsafe_allow_html=True)

    why = row.get("why_kazakhstan")
    if isinstance(why, str):
        try:
            why = json.loads(why)
        except Exception:
            why = [why]
    if why:
        st.markdown("**Почему Казахстан:**")
        for point in (why if isinstance(why, list) else [why]):
            st.markdown(f"• {point}")

    # ── E. Engagement Strategy ────────────────────────────────────────────
    st.markdown('<div class="section-header">E. Стратегия вовлечения</div>', unsafe_allow_html=True)

    st.markdown(f"""
    <div class="briefing-block">
        <div class="kpi-label">Форматы сотрудничества</div>
        <p style="margin:6px 0 0 0">{row.get('engagement_format', '—')}</p>
    </div>
    """, unsafe_allow_html=True)

    questions = row.get("negotiation_questions")
    if isinstance(questions, str):
        try:
            questions = json.loads(questions)
        except Exception:
            questions = [questions]
    if questions:
        st.markdown("**Вопросы для переговоров:**")
        for q in (questions if isinstance(questions, list) else [questions]):
            st.markdown(f"❓ {q}")

    # ── Sources ──────────────────────────────────────────────────────────
    sources = row.get("source_links", [])
    if isinstance(sources, str):
        try:
            sources = json.loads(sources)
        except Exception:
            sources = []
    if sources:
        st.markdown('<div class="section-header">Источники</div>', unsafe_allow_html=True)
        for url in sources:
            if url:
                st.markdown(f'<a class="source-link" href="{url}" target="_blank">🔗 {url}</a>',
                            unsafe_allow_html=True)

    # Re-research button
    st.markdown("---")
    if os.getenv("GOOGLE_API_KEY"):
        if st.button("🔄 Обновить AI исследование"):
            _run_single_research(row)


def _run_single_research(row):
    from ai_research import make_client, research_company
    with st.spinner(f"Исследую {row['company_name']}..."):
        client = make_client(os.environ["GOOGLE_API_KEY"])
        result = research_company(
            row["company_name"],
            row.get("sector"),
            row.get("industry_name"),
            client
        )
        save_research(row["company_name"], result)
    st.success("Исследование завершено!")
    st.rerun()


# ─── Router ──────────────────────────────────────────────────────────────────

def main():
    sidebar()
    page = st.session_state.page
    if page == "dashboard":
        page_dashboard()
    elif page == "companies":
        page_companies()
    elif page == "detail":
        page_detail()


if __name__ == "__main__":
    main()
