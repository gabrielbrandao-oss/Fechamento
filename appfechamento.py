# app_facilities.py — Dashboard Facilities Cobli
# Mesma identidade visual do HTML: dark mode, cores Cobli, Chart.js → Plotly
# Lê via gspread (service account) — funciona com planilha privada

import streamlit as st
import pandas as pd
import numpy as np
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import logging
import re, html as _html

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── TEMA COBLI (idêntico ao HTML) ───────────────────────────────────────────
st.set_page_config(
    page_title="Dashboard Facilities · Cobli",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DARK_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* Reset Streamlit para dark Cobli */
html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background-color: #0d1117 !important;
    color: #e6edf3 !important;
    font-family: 'Inter', -apple-system, sans-serif !important;
}
[data-testid="stSidebar"]  { background: #161b22 !important; }
[data-testid="stHeader"]   { background: #0d1117 !important; }
[data-testid="stToolbar"]  { display: none; }
footer                     { display: none; }

/* Blocos de métricas */
[data-testid="stMetric"] {
    background: #161b22;
    border: 1px solid #21283a;
    border-radius: 10px;
    padding: 16px 20px !important;
}
[data-testid="stMetricValue"]  { color: #e6edf3 !important; font-weight: 700; font-size: 1.6rem; }
[data-testid="stMetricLabel"]  { color: #7d8590 !important; font-size: .75rem; text-transform: uppercase; letter-spacing: .04em; }
[data-testid="stMetricDelta"]  { font-size: .8rem; }

/* Tabs */
[data-testid="stTabs"] button {
    background: #161b22 !important;
    color: #7d8590 !important;
    border-bottom: 2px solid transparent !important;
    border-radius: 0 !important;
    font-size: .85rem;
    font-weight: 500;
    padding: 10px 18px;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #2490d8 !important;
    border-bottom-color: #2490d8 !important;
    background: #0d1117 !important;
}

/* Selectbox / inputs */
[data-testid="stSelectbox"] > div > div,
[data-testid="stDateInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextInput"] input {
    background: #161b22 !important;
    border: 1px solid #21283a !important;
    border-radius: 8px !important;
    color: #e6edf3 !important;
    font-size: .85rem !important;
}
[data-testid="stSelectbox"] svg { fill: #7d8590 !important; }

/* Botões */
[data-testid="stButton"] > button {
    background: #1d6fa4 !important;
    color: #fff !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: .85rem !important;
    padding: 8px 18px !important;
    transition: background .15s;
}
[data-testid="stButton"] > button:hover { background: #2490d8 !important; }

/* Dataframe / tabelas */
[data-testid="stDataFrame"] { border: 1px solid #21283a; border-radius: 10px; overflow: hidden; }
[data-testid="stDataFrame"] th {
    background: #161b22 !important;
    color: #7d8590 !important;
    font-size: .75rem !important;
    text-transform: uppercase;
    letter-spacing: .04em;
    border-bottom: 1px solid #21283a !important;
}
[data-testid="stDataFrame"] td { color: #e6edf3 !important; font-size: .82rem !important; border-color: #21283a !important; }

/* Alertas */
[data-testid="stAlert"] { border-radius: 8px !important; font-size: .84rem; }

/* Divisores */
hr { border-color: #21283a !important; }

/* Card genérico */
.cobli-card {
    background: #161b22;
    border: 1px solid #21283a;
    border-radius: 10px;
    padding: 20px 24px;
    margin-bottom: 16px;
}
.cobli-title {
    font-size: .7rem;
    text-transform: uppercase;
    letter-spacing: .08em;
    color: #7d8590;
    margin-bottom: 4px;
}
.cobli-val { font-size: 1.5rem; font-weight: 700; color: #e6edf3; }
.cobli-sub { font-size: .75rem; color: #7d8590; margin-top: 2px; }
.green { color: #1da462 !important; }
.red   { color: #e85454 !important; }
.yellow{ color: #d4a017 !important; }
.blue  { color: #2490d8 !important; }

/* Header do dashboard */
.dash-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 20px 0 16px;
    border-bottom: 1px solid #21283a;
    margin-bottom: 20px;
}
.dash-header h1 { font-size: 1.2rem; font-weight: 700; color: #e6edf3; margin: 0; }
.dash-header span { font-size: .8rem; color: #7d8590; }
.badge {
    background: rgba(29,111,164,.15);
    color: #2490d8;
    border: 1px solid rgba(36,144,216,.3);
    border-radius: 20px;
    font-size: .7rem;
    font-weight: 600;
    padding: 2px 10px;
    margin-left: 8px;
}
</style>
"""
st.markdown(DARK_CSS, unsafe_allow_html=True)

# ─── CORES PLOTLY (dark Cobli) ────────────────────────────────────────────────
PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#7d8590", size=11),
    margin=dict(t=36, b=8, l=8, r=8),
    legend=dict(
        orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
        font=dict(size=10), bgcolor="rgba(0,0,0,0)", borderwidth=0,
    ),
    xaxis=dict(gridcolor="#21283a", linecolor="#21283a", tickfont=dict(size=10)),
    yaxis=dict(gridcolor="#21283a", linecolor="#21283a", tickfont=dict(size=10)),
)

COR_BUDGET    = "#1d6fa4"
COR_REALIZADO = "#1da462"
COR_DELTA     = "#d4a017"
COR_VERMELHO  = "#e85454"

PT_MONTHS = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
def fmt_mes(dt):
    if pd.isna(dt): return None
    return f"{PT_MONTHS[dt.month-1]}/{str(dt.year)[2:]}"

def fmt_brl(v):
    try: return f"R$ {float(v):,.2f}".replace(",","X").replace(".",",").replace("X",".")
    except: return "R$ 0,00"

# ─── AUTENTICAÇÃO ─────────────────────────────────────────────────────────────
def check_auth():
    # Aceita tanto senha em texto plano quanto hash bcrypt no secrets.toml
    # secrets.toml: senha_app = "cobli@1609"  ← texto plano funciona
    senha_cfg = st.secrets.get("senha_app", "")
    if not senha_cfg:
        # Tenta também a chave "senha_app_hash" para compatibilidade
        senha_cfg = st.secrets.get("senha_app_hash", "")
    if not senha_cfg:
        st.error("⚠️ Configure `senha_app` no secrets.toml  →  senha_app = \"sua_senha\"")
        st.stop()

    if st.session_state.get("auth_ok"):
        return True

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("""
        <div style='text-align:center; margin-bottom:24px;'>
            <div style='font-size:2rem;'>🏢</div>
            <div style='font-size:1.1rem; font-weight:700; color:#e6edf3; margin-top:8px;'>Dashboard Facilities</div>
            <div style='font-size:.8rem; color:#7d8590; margin-top:4px;'>Cobli · Acesso restrito</div>
        </div>
        """, unsafe_allow_html=True)

        senha = st.text_input("Senha", type="password", placeholder="Digite a senha de acesso")
        if st.button("Entrar", use_container_width=True):
            ok = False
            # 1. Tenta bcrypt (hash começando com $2b$ ou $2a$)
            if senha_cfg.startswith("$2"):
                try:
                    import bcrypt
                    ok = bcrypt.checkpw(senha.encode("utf-8"), senha_cfg.encode("utf-8"))
                except Exception:
                    ok = False
            # 2. Texto plano — comparação direta
            if not ok:
                ok = (senha == senha_cfg)
            if ok:
                st.session_state["auth_ok"] = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
    st.stop()

# ─── CONEXÃO GSPREAD ──────────────────────────────────────────────────────────
@st.cache_resource(ttl=3600)
def get_gspread_client():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        dict(st.secrets["gcp_service_account"]), scope
    )
    return gspread.authorize(creds)

# ─── ETL ──────────────────────────────────────────────────────────────────────
def parse_brl(serie: pd.Series) -> pd.Series:
    s = serie.astype(str).str.replace("R$","",regex=False).str.strip()
    s = s.str.replace(r'[^\d,.-]', '', regex=True)
    s = s.str.replace('.','',regex=False).str.replace(',','.',regex=False)
    return pd.to_numeric(s, errors='coerce').fillna(0.0)

@st.cache_data(ttl=60, show_spinner=False)
def load_budget(_client, url: str) -> pd.DataFrame:
    """Lê aba Budget e retorna DataFrame com colunas padronizadas."""
    sheet = _client.open_by_url(url)
    ws    = sheet.worksheet("Budget")
    data  = ws.get_all_values()
    if len(data) < 2:
        return pd.DataFrame()

    df = pd.DataFrame(data[1:], columns=data[0])
    df.columns = df.columns.str.strip().str.upper()

    # Mês
    col_mes = next((c for c in df.columns if c in ['MÊS','MES','DATA','PERÍODO']), None)
    if col_mes:
        df["_mes_dt"] = pd.to_datetime(df[col_mes], errors='coerce')
        df["Mes"]     = df["_mes_dt"].apply(fmt_mes)
        df["Ano"]     = df["_mes_dt"].dt.year.astype("Int64").astype(str)
    else:
        df["Mes"] = df["Ano"] = "?"

    # Conta
    df["Conta"] = df.get("TIPO 1", df.iloc[:, 2]).astype(str).str.strip()

    # Valores
    col_b = next((c for c in df.columns if c == 'BUDGET'), None)
    col_r = next((c for c in df.columns if c == 'REALIZADO'), None)
    col_d = next((c for c in df.columns if c == 'DELTA'), None)
    df["Budget"]    = parse_brl(df[col_b]) if col_b else 0.0
    df["Realizado"] = parse_brl(df[col_r]) if col_r else 0.0
    df["Delta"]     = parse_brl(df[col_d]) if col_d else (df["Budget"] - df["Realizado"])

    # Tipo (filtro Facilities)
    col_tipo = next((c for c in df.columns if c == 'TIPO'), None)
    df["Tipo"] = df[col_tipo].astype(str).str.strip() if col_tipo else "Facilities"

    # Centro de custo
    col_cc = next((c for c in df.columns if 'CENTRO' in c), None)
    df["CentroCusto"] = df[col_cc].astype(str).str.strip() if col_cc else ""

    # Filtrar só Facilities
    df = df[df["Tipo"].str.lower() == "facilities"].copy()
    df = df[df["Mes"].notna() & (df["Mes"] != "None")].copy()
    return df

@st.cache_data(ttl=60, show_spinner=False)
def load_mrr(_client, url: str) -> pd.DataFrame:
    try:
        sheet = _client.open_by_url(url)
        ws    = sheet.worksheet("MRR")
        data  = ws.get_all_values()
        if len(data) < 2: return pd.DataFrame()
        df = pd.DataFrame(data[1:], columns=data[0])
        df.columns = df.columns.str.strip().str.upper()
        col_mrr  = next((c for c in df.columns if 'MRR' in c), None)
        col_data = next((c for c in df.columns if c in ['DATA','DATE','MÊS','MES']), None)
        col_hc   = next((c for c in df.columns if c == 'HC'), None)
        if not col_mrr or not col_data: return pd.DataFrame()
        df["_dt"]  = pd.to_datetime(df[col_data], errors='coerce')
        df["Mes"]  = df["_dt"].apply(fmt_mes)
        df["MRR"]  = parse_brl(df[col_mrr])
        df["HC"]   = pd.to_numeric(df[col_hc], errors='coerce').fillna(0) if col_hc else 0
        return df[["Mes","MRR","HC"]].dropna(subset=["Mes"])
    except Exception as e:
        logger.warning(f"MRR não carregado: {e}")
        return pd.DataFrame()

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def mes_order(m: str) -> int:
    if not m or m == "?": return 9999
    try:
        mon, yr = m.split("/")
        return int(yr)*12 + PT_MONTHS.index(mon)
    except: return 9999

def kpi_card(label: str, value, sub: str = "", color: str = ""):
    color_class = f' class="{color}"' if color else ''
    st.markdown(f"""
    <div class="cobli-card" style="min-height:80px;">
        <div class="cobli-title">{label}</div>
        <div class="cobli-val"{color_class}>{value}</div>
        <div class="cobli-sub">{sub}</div>
    </div>
    """, unsafe_allow_html=True)

# ─── GRÁFICOS (dark Cobli) ────────────────────────────────────────────────────
def chart_bar_bvr(df_mes: pd.DataFrame) -> go.Figure:
    """Budget × Realizado por mês — barras agrupadas."""
    fig = go.Figure()
    fig.add_bar(name="Budget",    x=df_mes["Mes"], y=df_mes["Budget"],
                marker_color=COR_BUDGET,    marker_line_width=0,
                hovertemplate="%{x}<br>Budget: R$ %{y:,.0f}<extra></extra>")
    fig.add_bar(name="Realizado", x=df_mes["Mes"], y=df_mes["Realizado"],
                marker_color=COR_REALIZADO, marker_line_width=0,
                hovertemplate="%{x}<br>Realizado: R$ %{y:,.0f}<extra></extra>")
    fig.update_layout(**PLOTLY_LAYOUT, barmode="group",
                      title=dict(text="Budget × Realizado", font=dict(size=13, color="#e6edf3")))
    return fig

def chart_linha_bvr(df_mes: pd.DataFrame) -> go.Figure:
    """Budget × Realizado por mês — linhas."""
    fig = go.Figure()
    fig.add_scatter(name="Budget",    x=df_mes["Mes"], y=df_mes["Budget"],
                    mode="lines+markers", line=dict(color=COR_BUDGET, width=2),
                    marker=dict(size=5))
    fig.add_scatter(name="Realizado", x=df_mes["Mes"], y=df_mes["Realizado"],
                    mode="lines+markers", line=dict(color=COR_REALIZADO, width=2),
                    marker=dict(size=5))
    fig.update_layout(**PLOTLY_LAYOUT,
                      title=dict(text="Evolução Mensal", font=dict(size=13, color="#e6edf3")))
    return fig

def chart_delta(df_mes: pd.DataFrame) -> go.Figure:
    """Delta mensal (Budget − Realizado)."""
    cores = [COR_REALIZADO if v >= 0 else COR_VERMELHO for v in df_mes["Delta"]]
    fig = go.Figure()
    fig.add_bar(x=df_mes["Mes"], y=df_mes["Delta"],
                marker_color=cores, marker_line_width=0,
                hovertemplate="%{x}<br>Delta: R$ %{y:,.0f}<extra></extra>",
                name="Delta")
    fig.add_hline(y=0, line_color="#21283a", line_width=1)
    fig.update_layout(**PLOTLY_LAYOUT,
                      showlegend=False,
                      title=dict(text="Delta Mensal (Budget − Realizado)", font=dict(size=13, color="#e6edf3")))
    return fig

def chart_contas(df_contas: pd.DataFrame) -> go.Figure:
    """Top contas — barra horizontal."""
    top = df_contas.nlargest(10, "Realizado")
    fig = go.Figure()
    fig.add_bar(name="Budget",    y=top["Conta"], x=top["Budget"],
                orientation="h", marker_color=COR_BUDGET,    marker_line_width=0)
    fig.add_bar(name="Realizado", y=top["Conta"], x=top["Realizado"],
                orientation="h", marker_color=COR_REALIZADO, marker_line_width=0)
    layout = {**PLOTLY_LAYOUT, "barmode": "group", "height": 340,
              "yaxis": {**PLOTLY_LAYOUT["yaxis"], "autorange": "reversed"},
              "title": dict(text="Top Contas · Budget vs Realizado", font=dict(size=13, color="#e6edf3"))}
    fig.update_layout(**layout)
    return fig

def chart_mrr(df_mrr: pd.DataFrame, df_mes: pd.DataFrame) -> go.Figure:
    """MRR × Custo Facilities."""
    merged = pd.merge(df_mrr, df_mes[["Mes","Realizado"]], on="Mes", how="inner")
    if merged.empty: return go.Figure()
    fig = go.Figure()
    fig.add_bar(name="MRR", x=merged["Mes"], y=merged["MRR"],
                marker_color="#2490d8", marker_line_width=0, yaxis="y")
    fig.add_scatter(name="Custo Facilities", x=merged["Mes"], y=merged["Realizado"],
                    mode="lines+markers", line=dict(color=COR_VERMELHO, width=2),
                    marker=dict(size=5), yaxis="y2")
    layout = {
        **PLOTLY_LAYOUT,
        "yaxis":  dict(title="MRR (R$)",      side="left",  gridcolor="#21283a", tickfont=dict(size=10)),
        "yaxis2": dict(title="Facilities (R$)", side="right", overlaying="y", gridcolor="rgba(0,0,0,0)", tickfont=dict(size=10)),
        "title":  dict(text="MRR × Custo Facilities", font=dict(size=13, color="#e6edf3")),
    }
    fig.update_layout(**layout)
    return fig

def chart_centros(df_cc: pd.DataFrame) -> go.Figure:
    """Budget × Realizado por centro de custo."""
    fig = go.Figure()
    fig.add_bar(name="Budget",    y=df_cc["CentroCusto"], x=df_cc["Budget"],
                orientation="h", marker_color=COR_BUDGET,    marker_line_width=0)
    fig.add_bar(name="Realizado", y=df_cc["CentroCusto"], x=df_cc["Realizado"],
                orientation="h", marker_color=COR_REALIZADO, marker_line_width=0)
    layout = {**PLOTLY_LAYOUT, "barmode": "group", "height": 300,
              "yaxis": {**PLOTLY_LAYOUT["yaxis"], "autorange": "reversed"},
              "title": dict(text="Centro de Custo", font=dict(size=13, color="#e6edf3"))}
    fig.update_layout(**layout)
    return fig

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    check_auth()

    # Header
    st.markdown("""
    <div class="dash-header">
        <div>
            <h1>🏢 Dashboard Facilities <span class="badge">Cobli</span></h1>
            <span>Budget × Realizado · Facilities</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Logout
    with st.sidebar:
        st.markdown("### 🏢 Facilities")
        if st.button("🚪 Sair"):
            st.session_state["auth_ok"] = False
            st.rerun()
        st.markdown("---")
        auto_refresh = st.checkbox("🔄 Auto-refresh (60s)", value=True)
        if auto_refresh:
            st.markdown("""
            <script>setTimeout(function(){window.location.reload();}, 60000);</script>
            """, unsafe_allow_html=True)

    # Conectar
    url = st.secrets.get("url_planilha","")
    if not url:
        st.error("⚠️ `url_planilha` não configurada em secrets.toml")
        st.stop()

    with st.spinner("Lendo planilha…"):
        try:
            client  = get_gspread_client()
            df_raw  = load_budget(client, url)
            df_mrr  = load_mrr(client, url)
        except Exception as e:
            st.error(f"Erro ao conectar: {e}")
            st.stop()

    if df_raw.empty:
        st.warning("Nenhum dado Facilities encontrado na aba Budget.")
        st.stop()

    # ── FILTROS ──────────────────────────────────────────────────────────────
    st.markdown("---")
    anos_disp = sorted(df_raw["Ano"].dropna().unique(), reverse=True)
    anos_disp = [a for a in anos_disp if str(a).isdigit()]
    meses_todos = sorted(df_raw["Mes"].dropna().unique(), key=mes_order)

    fc1, fc2, fc3, fc4, fc5 = st.columns([1, 1.2, 1.4, 1.4, 1])
    with fc1:
        ano_sel = st.selectbox("Ano", ["Todos"] + anos_disp,
                               index=1 if "2026" in anos_disp else 0, key="ano")
    with fc2:
        df_filtrado_ano = df_raw[df_raw["Ano"] == ano_sel] if ano_sel != "Todos" else df_raw
        meses_ano = sorted(df_filtrado_ano["Mes"].dropna().unique(), key=mes_order)
        mes_sel = st.selectbox("Mês", ["Todos"] + list(meses_ano), key="mes")
    with fc3:
        contas_disp = sorted(df_raw["Conta"].dropna().unique())
        conta_sel = st.selectbox("Conta", ["Todas"] + contas_disp, key="conta")
    with fc4:
        cc_disp = sorted(df_raw["CentroCusto"].dropna().replace("","(sem centro)").unique())
        cc_sel = st.selectbox("Centro de Custo", ["Todos"] + [c for c in cc_disp if c], key="cc")
    with fc5:
        if st.button("↺ Atualizar", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # Aplicar filtros
    df = df_raw.copy()
    if ano_sel != "Todos":   df = df[df["Ano"] == ano_sel]
    if mes_sel != "Todos":   df = df[df["Mes"] == mes_sel]
    if conta_sel != "Todas": df = df[df["Conta"] == conta_sel]
    if cc_sel != "Todos":    df = df[df["CentroCusto"].replace("", "(sem centro)") == cc_sel]

    if df.empty:
        st.info("Nenhum dado para os filtros selecionados.")
        return

    # Agregações
    df_mes = (df.groupby("Mes", as_index=False)
               .agg(Budget=("Budget","sum"), Realizado=("Realizado","sum"), Delta=("Delta","sum"))
               .sort_values("Mes", key=lambda s: s.map(mes_order)))
    df_contas = (df.groupby("Conta", as_index=False)
                  .agg(Budget=("Budget","sum"), Realizado=("Realizado","sum"), Delta=("Delta","sum")))
    df_cc = (df[df["CentroCusto"] != ""].groupby("CentroCusto", as_index=False)
              .agg(Budget=("Budget","sum"), Realizado=("Realizado","sum"))
              .sort_values("Realizado", ascending=False))

    tot_budget    = df_mes["Budget"].sum()
    tot_realizado = df_mes["Realizado"].sum()
    tot_delta     = df_mes["Delta"].sum()
    pct_exec      = tot_realizado / tot_budget * 100 if tot_budget > 0 else 0

    # ── ABAS ─────────────────────────────────────────────────────────────────
    tab_geral, tab_contas, tab_centro, tab_mrr = st.tabs([
        "📊 Visão Geral", "📋 Por Conta", "🏢 Centro de Custo", "📈 MRR vs Custo"
    ])

    # ══════════════════════════════════════════════════════
    # ABA 1 — VISÃO GERAL
    # ══════════════════════════════════════════════════════
    with tab_geral:
        # KPIs
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            kpi_card("Total Budget", fmt_brl(tot_budget), f"{len(df_mes)} meses")
        with k2:
            cor = "red" if tot_realizado > tot_budget else "green"
            kpi_card("Total Realizado", fmt_brl(tot_realizado),
                     f"{pct_exec:.1f}% executado", cor)
        with k3:
            cor = "green" if tot_delta >= 0 else "red"
            sinal = "+" if tot_delta >= 0 else ""
            kpi_card("Delta (Economia)", f"{sinal}{fmt_brl(tot_delta)}",
                     "Abaixo do budget ✓" if tot_delta >= 0 else "Acima do budget ⚠️", cor)
        with k4:
            mes_maior = df_mes.loc[df_mes["Realizado"].idxmax(), "Mes"] if not df_mes.empty else "—"
            kpi_card("Maior Realizado", mes_maior,
                     fmt_brl(df_mes["Realizado"].max()) if not df_mes.empty else "—")

        st.markdown("---")

        # Gráfico principal — toggle barras/linha
        modo = st.radio("Tipo de gráfico", ["Barras", "Linha"], horizontal=True, key="modo_chart")
        if modo == "Barras":
            st.plotly_chart(chart_bar_bvr(df_mes), use_container_width=True)
        else:
            st.plotly_chart(chart_linha_bvr(df_mes), use_container_width=True)

        # Delta
        st.plotly_chart(chart_delta(df_mes), use_container_width=True)

    # ══════════════════════════════════════════════════════
    # ABA 2 — POR CONTA
    # ══════════════════════════════════════════════════════
    with tab_contas:
        st.plotly_chart(chart_contas(df_contas), use_container_width=True)
        st.markdown("---")
        st.markdown("##### Detalhamento por Conta")

        df_contas["% Exec"] = np.where(
            df_contas["Budget"] > 0,
            (df_contas["Realizado"] / df_contas["Budget"] * 100), 0)
        df_contas["Status"] = np.select(
            [df_contas["Realizado"] > df_contas["Budget"],
             df_contas["Realizado"] >= df_contas["Budget"] * 0.85],
            ["🔴 Estourou", "🟡 Alerta"], default="🟢 OK")

        st.dataframe(
            df_contas[["Status","Conta","Budget","Realizado","Delta","% Exec"]]
              .sort_values("Realizado", ascending=False).reset_index(drop=True),
            hide_index=True, use_container_width=True,
            column_config={
                "Status":    st.column_config.TextColumn("Alerta", width="small"),
                "Conta":     st.column_config.TextColumn("Conta"),
                "Budget":    st.column_config.NumberColumn("Budget",    format="R$ %.2f"),
                "Realizado": st.column_config.NumberColumn("Realizado", format="R$ %.2f"),
                "Delta":     st.column_config.NumberColumn("Delta",     format="R$ %.2f"),
                "% Exec":    st.column_config.ProgressColumn("Execução", format="%.1f%%", min_value=0, max_value=100),
            }
        )

    # ══════════════════════════════════════════════════════
    # ABA 3 — CENTRO DE CUSTO
    # ══════════════════════════════════════════════════════
    with tab_centro:
        if df_cc.empty:
            st.info("Nenhum Centro de Custo detectado na aba Budget (coluna 'Centro de Custo').")
        else:
            # KPIs de centro
            tot_cc_r = df_cc["Realizado"].sum()
            k1, k2, k3, k4 = st.columns(4)
            with k1: kpi_card("Centros Ativos", str(len(df_cc)), "com Facilities")
            with k2: kpi_card("Realizado Total", fmt_brl(tot_cc_r))
            with k3:
                maior = df_cc.iloc[0]
                kpi_card("Maior Centro", maior["CentroCusto"][:20], fmt_brl(maior["Realizado"]))
            with k4:
                menor = df_cc.iloc[-1]
                kpi_card("Menor Centro", menor["CentroCusto"][:20], fmt_brl(menor["Realizado"]))

            st.markdown("---")

            # Toggle: juntos / separados
            modo_cc = st.radio("Visualização", ["Juntos", "Separados"], horizontal=True, key="modo_cc")

            if modo_cc == "Juntos":
                st.plotly_chart(chart_centros(df_cc), use_container_width=True)
            else:
                # Mini-gráficos individuais por centro
                centros = df_cc["CentroCusto"].tolist()
                cols_mini = st.columns(min(3, len(centros)))
                for i, centro in enumerate(centros):
                    df_mini = df[df["CentroCusto"] == centro].groupby("Mes", as_index=False).agg(
                        Budget=("Budget","sum"), Realizado=("Realizado","sum"))
                    df_mini = df_mini.sort_values("Mes", key=lambda s: s.map(mes_order))
                    fig_mini = go.Figure()
                    fig_mini.add_bar(name="Budget",    x=df_mini["Mes"], y=df_mini["Budget"],
                                     marker_color=COR_BUDGET,    marker_line_width=0)
                    fig_mini.add_bar(name="Realizado", x=df_mini["Mes"], y=df_mini["Realizado"],
                                     marker_color=COR_REALIZADO, marker_line_width=0)
                    layout_mini = {**PLOTLY_LAYOUT, "barmode":"group", "height":200,
                                   "title":dict(text=centro[:24], font=dict(size=11, color="#e6edf3")),
                                   "showlegend": False,
                                   "margin": dict(t=30, b=4, l=4, r=4)}
                    fig_mini.update_layout(**layout_mini)
                    with cols_mini[i % 3]:
                        st.plotly_chart(fig_mini, use_container_width=True)

            st.markdown("---")
            st.markdown("##### Tabela por Centro de Custo")
            df_cc_tab = df_cc.copy()
            df_cc_tab["Delta"]  = df_cc_tab["Budget"] - df_cc_tab["Realizado"]
            df_cc_tab["% Exec"] = np.where(
                df_cc_tab["Budget"] > 0,
                df_cc_tab["Realizado"] / df_cc_tab["Budget"] * 100, 0)
            st.dataframe(
                df_cc_tab[["CentroCusto","Budget","Realizado","Delta","% Exec"]]
                  .sort_values("Realizado", ascending=False).reset_index(drop=True),
                hide_index=True, use_container_width=True,
                column_config={
                    "CentroCusto": st.column_config.TextColumn("Centro de Custo"),
                    "Budget":      st.column_config.NumberColumn("Budget",    format="R$ %.2f"),
                    "Realizado":   st.column_config.NumberColumn("Realizado", format="R$ %.2f"),
                    "Delta":       st.column_config.NumberColumn("Delta",     format="R$ %.2f"),
                    "% Exec":      st.column_config.ProgressColumn("Execução", format="%.1f%%", min_value=0, max_value=100),
                }
            )

    # ══════════════════════════════════════════════════════
    # ABA 4 — MRR VS CUSTO
    # ══════════════════════════════════════════════════════
    with tab_mrr:
        if df_mrr.empty:
            st.info("Aba MRR não encontrada ou sem dados.")
        else:
            df_mrr_fil = df_mrr.copy()
            if ano_sel != "Todos":
                df_mrr_fil = df_mrr_fil[df_mrr_fil["Mes"].str.endswith(ano_sel[2:])]

            merged = pd.merge(df_mrr_fil, df_mes[["Mes","Realizado"]], on="Mes", how="inner")
            if merged.empty:
                st.info("Sem sobreposição de meses entre MRR e Budget Facilities.")
            else:
                merged["% Custo/MRR"] = np.where(
                    merged["MRR"] > 0,
                    merged["Realizado"] / merged["MRR"] * 100, 0)

                # KPIs MRR
                k1, k2, k3 = st.columns(3)
                with k1: kpi_card("MRR Médio", fmt_brl(merged["MRR"].mean()))
                with k2: kpi_card("% Médio Facilities/MRR", f"{merged['% Custo/MRR'].mean():.2f}%")
                with k3: kpi_card("HC Médio", str(int(df_mrr_fil["HC"].mean())) if "HC" in df_mrr_fil else "—")

                st.markdown("---")
                st.plotly_chart(chart_mrr(df_mrr_fil, df_mes), use_container_width=True)
                st.markdown("---")
                st.dataframe(
                    merged[["Mes","MRR","Realizado","% Custo/MRR"]].sort_values("Mes", key=lambda s: s.map(mes_order)).reset_index(drop=True),
                    hide_index=True, use_container_width=True,
                    column_config={
                        "Mes":          st.column_config.TextColumn("Mês"),
                        "MRR":          st.column_config.NumberColumn("MRR", format="R$ %.2f"),
                        "Realizado":    st.column_config.NumberColumn("Facilities", format="R$ %.2f"),
                        "% Custo/MRR":  st.column_config.ProgressColumn("% Custo/MRR", format="%.2f%%", min_value=0, max_value=10),
                    }
                )

if __name__ == "__main__":
    main()
