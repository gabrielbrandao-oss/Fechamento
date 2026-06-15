# app_facilities.py — Dashboard Facilities Cobli
# Fonte Budget:      aba "Budget"      → D=Budget, E=Realizado, F=Delta, G=filtro Facilities
# Fonte Realizado:   aba "Query Geral" → N=Conta, O=filtro Facilities, P=Centro de Custo, D=Valor
# Auto-refresh 60s · gráficos juntos + separados por centro de custo

import streamlit as st
import pandas as pd
import numpy as np
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── CONFIG ──────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Dashboard Facilities · Cobli",
    page_icon="🏢", layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── TEMA COBLI ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html,body,[data-testid="stAppViewContainer"],[data-testid="stMain"]{
  background:#0d1117!important;color:#e6edf3!important;
  font-family:'Inter',-apple-system,sans-serif!important;}
[data-testid="stSidebar"]{background:#161b22!important;}
[data-testid="stHeader"]{background:#0d1117!important;}
[data-testid="stToolbar"],footer{display:none!important;}
section[data-testid="stMain"]>div{padding-top:16px!important;}
/* Métricas */
[data-testid="stMetric"]{background:#161b22;border:1px solid #21283a;
  border-radius:10px;padding:16px 20px!important;}
[data-testid="stMetricValue"]{color:#e6edf3!important;font-weight:700;font-size:1.5rem!important;}
[data-testid="stMetricLabel"]{color:#7d8590!important;font-size:.7rem!important;
  text-transform:uppercase;letter-spacing:.05em;}
/* Tabs */
[data-testid="stTabs"] button{background:#161b22!important;color:#7d8590!important;
  border-bottom:2px solid transparent!important;border-radius:0!important;
  font-size:.83rem;font-weight:500;padding:10px 18px;}
[data-testid="stTabs"] button[aria-selected="true"]{color:#2490d8!important;
  border-bottom-color:#2490d8!important;background:#0d1117!important;}
/* Inputs */
[data-testid="stSelectbox"]>div>div,[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,[data-testid="stDateInput"] input{
  background:#161b22!important;border:1px solid #21283a!important;
  border-radius:8px!important;color:#e6edf3!important;font-size:.83rem!important;}
[data-testid="stSelectbox"] svg{fill:#7d8590!important;}
/* Botões */
[data-testid="stButton"]>button{background:#1d6fa4!important;color:#fff!important;
  border:none!important;border-radius:8px!important;font-weight:600!important;
  font-size:.83rem!important;padding:8px 18px!important;}
[data-testid="stButton"]>button:hover{background:#2490d8!important;}
/* Radio */
[data-testid="stRadio"] label{color:#7d8590!important;font-size:.82rem!important;}
[data-testid="stRadio"] [aria-checked="true"] + div{color:#e6edf3!important;}
/* Dataframe */
[data-testid="stDataFrame"]{border:1px solid #21283a;border-radius:10px;overflow:hidden;}
[data-testid="stDataFrame"] th{background:#161b22!important;color:#7d8590!important;
  font-size:.72rem!important;text-transform:uppercase;letter-spacing:.04em;
  border-bottom:1px solid #21283a!important;}
[data-testid="stDataFrame"] td{color:#e6edf3!important;font-size:.8rem!important;
  border-color:#21283a!important;}
hr{border-color:#21283a!important;}
/* Card KPI custom */
.kpi-card{background:#161b22;border:1px solid #21283a;border-radius:10px;
  padding:16px 20px;height:100%;}
.kpi-label{font-size:.68rem;text-transform:uppercase;letter-spacing:.06em;color:#7d8590;margin-bottom:4px;}
.kpi-val{font-size:1.45rem;font-weight:700;color:#e6edf3;line-height:1.2;}
.kpi-sub{font-size:.72rem;color:#7d8590;margin-top:3px;}
.green{color:#1da462!important;} .red{color:#e85454!important;}
.yellow{color:#d4a017!important;} .blue{color:#2490d8!important;}
/* Toggle buttons */
.toggle-wrap{display:flex;gap:6px;margin-bottom:8px;}
</style>
""", unsafe_allow_html=True)

# ─── CONSTANTES ──────────────────────────────────────────────────────────────
PT = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
C_BUD = "#1d6fa4";  C_REAL = "#1da462";  C_VERM = "#e85454"
C_DELTA = "#d4a017"; C_BLUE = "#2490d8"
PALETTE = ["#2490d8","#1da462","#d4a017","#e85454","#a064c8",
           "#50c8c8","#e6823c","#78a05a","#c878a0","#6488dc",
           "#b4b45a","#8c8c8c"]

PLOTLY_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter,sans-serif", color="#7d8590", size=11),
    margin=dict(t=40,b=8,l=8,r=8),
    legend=dict(orientation="h",yanchor="bottom",y=1.02,xanchor="right",x=1,
                font=dict(size=10),bgcolor="rgba(0,0,0,0)"),
    xaxis=dict(gridcolor="#21283a",linecolor="#21283a",tickfont=dict(size=10,color="#7d8590")),
    yaxis=dict(gridcolor="#21283a",linecolor="#21283a",tickfont=dict(size=10,color="#7d8590")),
)

def title_layout(txt):
    return dict(text=txt, font=dict(size=13,color="#e6edf3"), x=0, xanchor="left")

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def fmt_mes(dt):
    if pd.isna(dt): return None
    try: return f"{PT[dt.month-1]}/{str(dt.year)[2:]}"
    except: return None

def mes_ord(m):
    if not m or m=="?": return 9999
    try: mon,yr = m.split("/"); return int(yr)*12+PT.index(mon)
    except: return 9999

def brl(v):
    try:
        v = float(v)
        return f"R$ {abs(v):,.2f}".replace(",","X").replace(".",",").replace("X",".")
    except: return "R$ 0,00"

def parse_num(s):
    s = str(s).replace("R$","").strip()
    s = s.replace(".","").replace(",",".")
    try: return float(s)
    except: return 0.0

def kpi(label, val, sub="", color=""):
    c = f' class="{color}"' if color else ""
    st.markdown(f"""
    <div class="kpi-card">
      <div class="kpi-label">{label}</div>
      <div class="kpi-val"{c}>{val}</div>
      <div class="kpi-sub">{sub}</div>
    </div>""", unsafe_allow_html=True)

# ─── AUTH ─────────────────────────────────────────────────────────────────────
def check_auth():
    pwd = st.secrets.get("senha_app","") or st.secrets.get("senha_app_hash","")
    if not pwd:
        st.error("Configure `senha_app` no secrets.toml"); st.stop()
    if st.session_state.get("_ok"): return
    _,col,_ = st.columns([1,1.1,1])
    with col:
        st.markdown("<br><br>",unsafe_allow_html=True)
        st.markdown("""<div style='text-align:center;margin-bottom:20px'>
        <div style='font-size:2rem'>🏢</div>
        <div style='font-size:1.1rem;font-weight:700;color:#e6edf3;margin-top:8px'>
            Dashboard Facilities</div>
        <div style='font-size:.8rem;color:#7d8590;margin-top:4px'>Cobli · Acesso restrito</div>
        </div>""", unsafe_allow_html=True)
        s = st.text_input("Senha", type="password", placeholder="Digite a senha")
        if st.button("Entrar", use_container_width=True):
            ok = False
            if pwd.startswith("$2"):
                try:
                    import bcrypt
                    ok = bcrypt.checkpw(s.encode(), pwd.encode())
                except: pass
            if not ok: ok = (s == pwd)
            if ok: st.session_state["_ok"] = True; st.rerun()
            else: st.error("Senha incorreta.")
    st.stop()

# ─── GSPREAD ─────────────────────────────────────────────────────────────────
@st.cache_resource(ttl=3600)
def get_client():
    scope = ["https://spreadsheets.google.com/feeds",
             "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        dict(st.secrets["gcp_service_account"]), scope)
    return gspread.authorize(creds)

# ─── ETL ─────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def load_query_geral(_cli, url):
    """
    Query Geral → lançamentos realizados de Facilities
    Acesso por ÍNDICE de coluna (evita problema de colunas duplicadas no cabeçalho):
      col 0  (A) = Mês
      col 3  (D) = Débito/crédito (MC) = Valor realizado
      col 13 (N) = Conta Contabil
      col 14 (O) = Centro de Custo 2 → filtro "Facilities"
      col 15 (P) = Pacote 2          → Centro de Custo do dashboard
    """
    ws   = _cli.open_by_url(url).worksheet("Query Geral")
    data = ws.get_all_values()
    if len(data) < 2: return pd.DataFrame()

    rows = data[1:]  # ignora cabeçalho — acessa por índice
    records = []
    for r in rows:
        # Garantir que a linha tem colunas suficientes
        def get(i): return r[i].strip() if i < len(r) else ""
        tipo = get(14).lower()  # col O: deve ser "facilities"
        if tipo != "facilities":
            continue
        records.append({
            "_mes_raw":   get(0),
            "_valor_raw": get(3),
            "Conta":      get(13),
            "CentroCusto": get(15) or "(sem centro)",
        })

    if not records:
        return pd.DataFrame(columns=["Mes","Ano","Conta","CentroCusto","Valor"])

    df = pd.DataFrame(records)
    df["_dt"]  = pd.to_datetime(df["_mes_raw"], errors="coerce")
    df["Mes"]  = df["_dt"].apply(fmt_mes)
    df["Ano"]  = df["_dt"].dt.year.astype("Int64").astype(str)
    df["Valor"] = df["_valor_raw"].apply(parse_num)
    df["Conta"] = df["Conta"].astype(str).str.strip()
    df["CentroCusto"] = df["CentroCusto"].astype(str).str.strip()
    df.loc[df["CentroCusto"]=="", "CentroCusto"] = "(sem centro)"

    return df[["Mes","Ano","Conta","CentroCusto","Valor"]].dropna(subset=["Mes"])


@st.cache_data(ttl=60, show_spinner=False)
def load_budget(_cli, url):
    """
    Budget → orçamento oficial. Acesso por ÍNDICE (sem depender de cabeçalho):
      col 0 (A) = MÊS
      col 2 (C) = TIPO 1 (nome da conta)
      col 3 (D) = BUDGET
      col 4 (E) = REALIZADO
      col 5 (F) = DELTA
      col 6 (G) = TIPO → filtro "Facilities"
    """
    ws   = _cli.open_by_url(url).worksheet("Budget")
    data = ws.get_all_values()
    if len(data) < 2: return pd.DataFrame()

    # Detecta índices pelo cabeçalho com fallback para posição fixa
    hdr = [str(v).strip().upper() for v in data[0]]
    def idx(names, fallback):
        for n in names:
            try: return hdr.index(n)
            except ValueError: pass
        return fallback

    i_mes   = idx(["MÊS","MES","DATA"], 0)
    i_conta = idx(["TIPO 1"], 2)
    i_bud   = idx(["BUDGET"], 3)
    i_real  = idx(["REALIZADO"], 4)
    i_delta = idx(["DELTA"], 5)
    i_tipo  = idx(["TIPO"], 6)

    records = []
    for r in data[1:]:
        def get(i): return r[i].strip() if i < len(r) else ""
        # Sem filtro por TIPO: Budget inclui Facilities + IT & Softwares + Third-party Services
        # O filtro Facilities já é feito na Query Geral (coluna O)
        # Linhas completamente vazias são ignoradas
        if not get(i_mes) and not get(i_bud):
            continue
        records.append({
            "_mes_raw":  get(i_mes),
            "Conta":     get(i_conta),
            "Tipo":      get(i_tipo),
            "_bud_raw":  get(i_bud),
            "_real_raw": get(i_real),
            "_dlt_raw":  get(i_delta),
        })

    if not records:
        return pd.DataFrame(columns=["Mes","Ano","Conta","Budget","Realizado","Delta"])

    df = pd.DataFrame(records)
    df["_dt"]      = pd.to_datetime(df["_mes_raw"], errors="coerce")
    df["Mes"]      = df["_dt"].apply(fmt_mes)
    df["Ano"]      = df["_dt"].dt.year.astype("Int64").astype(str)
    df["Conta"]    = df["Conta"].astype(str).str.strip()
    df["Budget"]   = df["_bud_raw"].apply(parse_num)
    df["Realizado"]= df["_real_raw"].apply(parse_num)
    df["Delta"]    = df["_dlt_raw"].apply(parse_num)

    df["Tipo"] = df["Tipo"].astype(str).str.strip()
    return df[["Mes","Ano","Conta","Tipo","Budget","Realizado","Delta"]].dropna(subset=["Mes"])


@st.cache_data(ttl=60, show_spinner=False)
def load_mrr(_cli, url):
    try:
        ws   = _cli.open_by_url(url).worksheet("MRR")
        data = ws.get_all_values()
        if len(data) < 2: return pd.DataFrame()
        hdr = [str(v).strip().upper() for v in data[0]]
        def idx(names, fallback):
            for n in names:
                try: return hdr.index(n)
                except ValueError: pass
            return fallback
        i_mrr  = idx(["R$ MRR","MRR"], 0)
        i_data = idx(["DATA","DATE","MÊS","MES"], 1)
        i_hc   = idx(["HC"], 2)
        records = []
        for r in data[1:]:
            def get(i): return r[i].strip() if i < len(r) else ""
            records.append({
                "_dt_raw": get(i_data),
                "MRR":     parse_num(get(i_mrr)),
                "HC":      parse_num(get(i_hc)),
            })
        df = pd.DataFrame(records)
        df["Mes"] = pd.to_datetime(df["_dt_raw"], errors="coerce").apply(fmt_mes)
        return df[["Mes","MRR","HC"]].dropna(subset=["Mes"])
    except Exception as e:
        logger.warning(f"MRR: {e}"); return pd.DataFrame()

# ─── GRÁFICOS ─────────────────────────────────────────────────────────────────
def fig_bvr_barras(df):
    fig = go.Figure()
    fig.add_bar(name="Budget",    x=df["Mes"], y=df["Budget"],
                marker_color=C_BUD,  marker_line_width=0,
                hovertemplate="%{x}<br>Budget: R$ %{y:,.0f}<extra></extra>")
    fig.add_bar(name="Realizado", x=df["Mes"], y=df["Realizado"],
                marker_color=C_REAL, marker_line_width=0,
                hovertemplate="%{x}<br>Realizado: R$ %{y:,.0f}<extra></extra>")
    fig.update_layout(**PLOTLY_BASE, barmode="group",
                      title=title_layout("Budget × Realizado por Mês"))
    return fig

def fig_bvr_linha(df):
    fig = go.Figure()
    fig.add_scatter(name="Budget",    x=df["Mes"], y=df["Budget"],
                    mode="lines+markers", line=dict(color=C_BUD,width=2),marker=dict(size=5))
    fig.add_scatter(name="Realizado", x=df["Mes"], y=df["Realizado"],
                    mode="lines+markers", line=dict(color=C_REAL,width=2),marker=dict(size=5))
    fig.update_layout(**PLOTLY_BASE, title=title_layout("Evolução Mensal"))
    return fig

def fig_delta(df):
    cores = [C_REAL if v>=0 else C_VERM for v in df["Delta"]]
    fig = go.Figure()
    fig.add_bar(x=df["Mes"], y=df["Delta"], marker_color=cores,
                marker_line_width=0, name="Delta",
                hovertemplate="%{x}<br>Delta: R$ %{y:,.0f}<extra></extra>")
    fig.add_hline(y=0, line_color="#21283a", line_width=1)
    fig.update_layout(**PLOTLY_BASE, showlegend=False,
                      title=title_layout("Delta Mensal (Budget − Realizado)"))
    return fig

def fig_contas_horiz(df_c):
    top = df_c.nlargest(12,"Realizado")
    fig = go.Figure()
    fig.add_bar(name="Budget",    y=top["Conta"], x=top["Budget"],
                orientation="h", marker_color=C_BUD,  marker_line_width=0)
    fig.add_bar(name="Realizado", y=top["Conta"], x=top["Realizado"],
                orientation="h", marker_color=C_REAL, marker_line_width=0)
    layout = {**PLOTLY_BASE,"barmode":"group","height":360,
              "yaxis":{**PLOTLY_BASE["yaxis"],"autorange":"reversed"},
              "title":title_layout("Top Contas · Budget vs Realizado")}
    fig.update_layout(**layout)
    return fig

def fig_cc_juntos(df_cc):
    """Todos os centros de custo lado a lado + empilhado."""
    fig = go.Figure()
    fig.add_bar(name="Budget",    y=df_cc["CentroCusto"], x=df_cc["Budget"],
                orientation="h", marker_color=C_BUD,  marker_line_width=0)
    fig.add_bar(name="Realizado", y=df_cc["CentroCusto"], x=df_cc["Realizado"],
                orientation="h", marker_color=C_REAL, marker_line_width=0)
    layout = {**PLOTLY_BASE,"barmode":"group","height":320,
              "yaxis":{**PLOTLY_BASE["yaxis"],"autorange":"reversed"},
              "title":title_layout("Budget × Realizado por Centro de Custo")}
    fig.update_layout(**layout)
    return fig

def fig_cc_empilhado_mes(df_qg, meses_ord):
    """Realizado empilhado por mês, cor por centro de custo."""
    centros = sorted(df_qg["CentroCusto"].unique())
    fig = go.Figure()
    for i, cc in enumerate(centros):
        sub = df_qg[df_qg["CentroCusto"]==cc].groupby("Mes")["Valor"].sum().reindex(meses_ord, fill_value=0)
        fig.add_bar(name=cc, x=meses_ord, y=sub.values,
                    marker_color=PALETTE[i%len(PALETTE)], marker_line_width=0)
    fig.update_layout(**PLOTLY_BASE, barmode="stack",
                      title=title_layout("Realizado por Mês — empilhado por Centro"))
    return fig

def fig_cc_separados(df_qg_filt, df_bud_filt, centros, meses_ord):
    """Um mini-gráfico por centro de custo."""
    n = len(centros)
    if n == 0: return None
    cols = min(3, n)
    rows = (n + cols - 1) // cols
    subtitles = [cc[:22] for cc in centros]
    fig = make_subplots(rows=rows, cols=cols, subplot_titles=subtitles,
                        vertical_spacing=0.12, horizontal_spacing=0.06)
    for idx, cc in enumerate(centros):
        row, col = divmod(idx, cols)
        row += 1; col += 1
        # Realizado da Query Geral
        r_mes = (df_qg_filt[df_qg_filt["CentroCusto"]==cc]
                 .groupby("Mes")["Valor"].sum()
                 .reindex(meses_ord, fill_value=0))
        # Budget: não há CC na aba Budget → usa total dividido por nº centros ou mostra só realizado
        fig.add_bar(name="Realizado", x=meses_ord, y=r_mes.values,
                    marker_color=PALETTE[idx%len(PALETTE)], marker_line_width=0,
                    showlegend=(idx==0), row=row, col=col)
        fig.update_xaxes(tickfont=dict(size=8,color="#7d8590"),
                         gridcolor="#21283a", row=row, col=col)
        fig.update_yaxes(tickfont=dict(size=8,color="#7d8590"),
                         gridcolor="#21283a", row=row, col=col)
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Inter,sans-serif",color="#7d8590",size=10),
                      height=max(220*rows, 300),
                      margin=dict(t=40,b=8,l=8,r=8),
                      showlegend=False,
                      title=title_layout("Realizado por Centro de Custo — Separados"))
    for ann in fig.layout.annotations:
        ann.font.color = "#e6edf3"; ann.font.size = 11
    return fig

def fig_mrr(df_mrr, df_mes):
    m = pd.merge(df_mrr, df_mes[["Mes","Realizado"]], on="Mes", how="inner")
    if m.empty: return None
    fig = make_subplots(specs=[[{"secondary_y":True}]])
    fig.add_bar(name="MRR", x=m["Mes"], y=m["MRR"],
                marker_color=C_BLUE, marker_line_width=0,
                secondary_y=False)
    fig.add_scatter(name="Facilities", x=m["Mes"], y=m["Realizado"],
                    mode="lines+markers", line=dict(color=C_VERM,width=2),
                    marker=dict(size=5), secondary_y=True)
    fig.update_layout(**PLOTLY_BASE, title=title_layout("MRR × Custo Facilities"))
    fig.update_yaxes(title_text="MRR",        secondary_y=False,
                     gridcolor="#21283a", tickfont=dict(size=10,color="#7d8590"))
    fig.update_yaxes(title_text="Facilities", secondary_y=True,
                     gridcolor="rgba(0,0,0,0)", tickfont=dict(size=10,color="#7d8590"))
    return fig

# ─── MAIN ────────────────────────────────────────────────────────────────────
def main():
    check_auth()

    # Header
    st.markdown("""
    <div style='display:flex;align-items:center;gap:10px;
                padding:16px 0 12px;border-bottom:1px solid #21283a;margin-bottom:18px;'>
      <div>
        <div style='font-size:1.15rem;font-weight:700;color:#e6edf3;'>
          🏢 Dashboard Facilities
          <span style='background:rgba(29,111,164,.15);color:#2490d8;
                border:1px solid rgba(36,144,216,.3);border-radius:20px;
                font-size:.7rem;font-weight:600;padding:2px 10px;margin-left:8px;'>
            Cobli</span>
        </div>
        <div style='font-size:.78rem;color:#7d8590;margin-top:2px;'>
          Budget · Realizado · Facilities — Query Geral + aba Budget</div>
      </div>
    </div>""", unsafe_allow_html=True)

    # Sidebar
    with st.sidebar:
        st.markdown("### Facilities")
        if st.button("🚪 Sair"):
            st.session_state["_ok"] = False; st.rerun()
        st.markdown("---")
        if st.checkbox("🔄 Auto-refresh 60s", value=True):
            st.markdown("<script>setTimeout(()=>location.reload(),60000)</script>",
                        unsafe_allow_html=True)

    url = st.secrets.get("url_planilha","")
    if not url: st.error("Configure `url_planilha` no secrets.toml"); st.stop()

    # Carregar dados
    with st.spinner("Lendo planilha…"):
        try:
            cli    = get_client()
            df_qg  = load_query_geral(cli, url)  # Query Geral: lançamentos realizados
            df_bud = load_budget(cli, url)        # Budget: orçado/realizado/delta
            df_mrr = load_mrr(cli, url)
        except Exception as e:
            st.error(f"Erro ao ler planilha: {e}"); st.stop()

    if df_qg.empty and df_bud.empty:
        st.warning("Nenhum dado Facilities encontrado."); return

    # ── FILTROS ──────────────────────────────────────────────────────────────
    st.markdown("---")
    anos_bud = sorted(df_bud["Ano"].dropna().unique(), reverse=True) if not df_bud.empty else []
    anos_qg  = sorted(df_qg["Ano"].dropna().unique(),  reverse=True) if not df_qg.empty else []
    anos_all = sorted(set(anos_bud+anos_qg), reverse=True)
    anos_all = [a for a in anos_all if str(a).isdigit()]

    c1,c2,c3,c4,c5,c6 = st.columns([.8,1,1.2,1.3,1.2,.9])
    with c1:
        ano = st.selectbox("Ano", ["Todos"]+anos_all,
                           index=1 if "2026" in anos_all else 0)
    with c2:
        df_bud_a = df_bud[df_bud["Ano"]==ano] if ano!="Todos" else df_bud
        df_qg_a  = df_qg[df_qg["Ano"]==ano]   if ano!="Todos" else df_qg
        meses = sorted(set(df_bud_a["Mes"].dropna()) | set(df_qg_a["Mes"].dropna()), key=mes_ord)
        mes = st.selectbox("Mês", ["Todos"]+meses)
    with c3:
        # Filtro de Tipo (Facilities / IT & Softwares / Third-party Services / Todos)
        tipos_disp = sorted(df_bud_a["Tipo"].dropna().unique()) if not df_bud_a.empty else []
        tipo_sel = st.selectbox("Tipo", ["Todos"]+tipos_disp)
    with c4:
        df_bud_at = df_bud_a[df_bud_a["Tipo"]==tipo_sel] if tipo_sel!="Todos" else df_bud_a
        contas = sorted(set(df_bud_at["Conta"].dropna()) | set(df_qg_a["Conta"].dropna()))
        conta = st.selectbox("Conta", ["Todas"]+contas)
    with c5:
        ccs = sorted(df_qg_a["CentroCusto"].dropna().unique()) if not df_qg_a.empty else []
        cc_sel = st.selectbox("Centro de Custo", ["Todos"]+ccs)
    with c6:
        if st.button("↺ Atualizar", use_container_width=True):
            st.cache_data.clear(); st.rerun()

    # Aplicar filtros
    fb = df_bud.copy()
    fq = df_qg.copy()
    if ano      != "Todos": fb=fb[fb["Ano"]==ano];         fq=fq[fq["Ano"]==ano]
    if mes      != "Todos": fb=fb[fb["Mes"]==mes];         fq=fq[fq["Mes"]==mes]
    if tipo_sel != "Todos": fb=fb[fb["Tipo"]==tipo_sel]
    if conta    != "Todas": fb=fb[fb["Conta"]==conta];     fq=fq[fq["Conta"]==conta]
    if cc_sel   != "Todos": fq=fq[fq["CentroCusto"]==cc_sel]

    if fb.empty and fq.empty:
        st.info("Nenhum dado para os filtros selecionados."); return

    # Agregações base
    df_mes = (fb.groupby("Mes", as_index=False)
               .agg(Budget=("Budget","sum"),Realizado=("Realizado","sum"),Delta=("Delta","sum"))
               .sort_values("Mes", key=lambda s: s.map(mes_ord)))
    meses_ord = df_mes["Mes"].tolist()

    df_contas = (fb.groupby("Conta", as_index=False)
                  .agg(Budget=("Budget","sum"),Realizado=("Realizado","sum"),Delta=("Delta","sum")))

    df_cc_bud = (fb.groupby("Conta", as_index=False)  # Budget não tem CC → agrupa por conta
                   .agg(Budget=("Budget","sum"),Realizado=("Realizado","sum")))

    # Realizado da Query Geral por centro de custo (coluna P)
    df_cc_real = (fq.groupby("CentroCusto", as_index=False)
                    .agg(Realizado_QG=("Valor","sum"))
                    .sort_values("Realizado_QG", ascending=False))

    tot_budget    = df_mes["Budget"].sum()
    tot_realizado = df_mes["Realizado"].sum()
    tot_delta     = df_mes["Delta"].sum()
    pct           = tot_realizado/tot_budget*100 if tot_budget>0 else 0

    # ── ABAS ─────────────────────────────────────────────────────────────────
    tab1,tab2,tab3,tab4,tab5 = st.tabs([
        "📊 Visão Geral",
        "📋 Por Conta",
        "🏢 Centro de Custo",
        "📈 MRR vs Custo",
        "🔎 Lançamentos (Query Geral)",
    ])

    # ══════════════════════════════════════════════════════════════════════════
    # ABA 1 — VISÃO GERAL
    # ══════════════════════════════════════════════════════════════════════════
    with tab1:
        k1,k2,k3,k4 = st.columns(4)
        with k1: kpi("Total Budget", brl(tot_budget), f"{len(df_mes)} meses")
        with k2:
            cor = "red" if tot_realizado>tot_budget else "green"
            kpi("Realizado (Budget)", brl(tot_realizado), f"{pct:.1f}% executado", cor)
        with k3:
            cor = "green" if tot_delta>=0 else "red"
            kpi("Delta", ("+" if tot_delta>=0 else "")+brl(tot_delta),
                "Abaixo do budget ✓" if tot_delta>=0 else "Acima do budget ⚠️", cor)
        with k4:
            tot_qg = fq["Valor"].sum()
            kpi("Realizado (Query Geral)", brl(tot_qg),
                f"{len(fq):,} lançamentos", "blue")

        st.markdown("---")

        modo = st.radio("Gráfico", ["Barras","Linha"], horizontal=True, key="g1")
        if not df_mes.empty:
            st.plotly_chart(fig_bvr_barras(df_mes) if modo=="Barras" else fig_bvr_linha(df_mes),
                            use_container_width=True)
            st.plotly_chart(fig_delta(df_mes), use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════════
    # ABA 2 — POR CONTA
    # ══════════════════════════════════════════════════════════════════════════
    with tab2:
        if df_contas.empty:
            st.info("Sem dados de contas.")
        else:
            st.plotly_chart(fig_contas_horiz(df_contas), use_container_width=True)
            st.markdown("---")
            df_contas["%Exec"] = np.where(
                df_contas["Budget"]>0,
                df_contas["Realizado"]/df_contas["Budget"]*100, 0)
            df_contas["Status"] = np.select(
                [df_contas["Realizado"]>df_contas["Budget"],
                 df_contas["Realizado"]>=df_contas["Budget"]*0.85],
                ["🔴 Estourou","🟡 Alerta"], default="🟢 OK")
            st.dataframe(
                df_contas[["Status","Conta","Budget","Realizado","Delta","%Exec"]]
                  .sort_values("Realizado",ascending=False).reset_index(drop=True),
                hide_index=True, use_container_width=True,
                column_config={
                    "Status":    st.column_config.TextColumn("Alerta",width="small"),
                    "Conta":     st.column_config.TextColumn("Conta"),
                    "Budget":    st.column_config.NumberColumn("Budget",    format="R$ %.2f"),
                    "Realizado": st.column_config.NumberColumn("Realizado", format="R$ %.2f"),
                    "Delta":     st.column_config.NumberColumn("Delta",     format="R$ %.2f"),
                    "%Exec":     st.column_config.ProgressColumn("Execução",format="%.1f%%",
                                                                 min_value=0,max_value=100),
                })

    # ══════════════════════════════════════════════════════════════════════════
    # ABA 3 — CENTRO DE CUSTO  (coluna P da Query Geral)
    # ══════════════════════════════════════════════════════════════════════════
    with tab3:
        if fq.empty:
            st.info("Sem lançamentos Facilities na Query Geral para os filtros selecionados.")
        else:
            # KPIs
            k1,k2,k3,k4 = st.columns(4)
            with k1: kpi("Centros Ativos", str(len(df_cc_real)), "col P · Facilities")
            with k2: kpi("Realizado Total", brl(df_cc_real["Realizado_QG"].sum()))
            with k3:
                m_cc = df_cc_real.iloc[0] if not df_cc_real.empty else None
                kpi("Maior Centro", m_cc["CentroCusto"][:22] if m_cc is not None else "—",
                    brl(m_cc["Realizado_QG"]) if m_cc is not None else "")
            with k4:
                mn_cc = df_cc_real.iloc[-1] if not df_cc_real.empty else None
                kpi("Menor Centro", mn_cc["CentroCusto"][:22] if mn_cc is not None else "—",
                    brl(mn_cc["Realizado_QG"]) if mn_cc is not None else "")

            st.markdown("---")

            # Toggle JUNTOS / SEPARADOS
            modo_cc = st.radio("Visualização", ["Juntos","Separados"], horizontal=True, key="g_cc")

            centros_lista = df_cc_real["CentroCusto"].tolist()
            meses_qg_ord  = sorted(fq["Mes"].dropna().unique(), key=mes_ord)

            if modo_cc == "Juntos":
                # Gráfico 1 — barras lado a lado
                # Monta df com Budget agregado por centro (via conta) e Realizado da QG
                st.plotly_chart(fig_cc_juntos(
                    df_cc_real.rename(columns={"Realizado_QG":"Realizado"})
                              .assign(Budget=0)),  # Budget não tem CC → sem barra Budget aqui
                    use_container_width=True)
                # Gráfico 2 — empilhado por mês
                st.plotly_chart(fig_cc_empilhado_mes(fq, meses_qg_ord),
                                use_container_width=True)
            else:
                # Mini-gráfico por centro
                fig_sep = fig_cc_separados(fq, fb, centros_lista, meses_qg_ord)
                if fig_sep: st.plotly_chart(fig_sep, use_container_width=True)

            st.markdown("---")
            st.markdown("##### Tabela por Centro de Custo")
            df_cc_tab = df_cc_real.copy()
            df_cc_tab["%Total"] = np.where(
                df_cc_tab["Realizado_QG"].sum()>0,
                df_cc_tab["Realizado_QG"]/df_cc_tab["Realizado_QG"].sum()*100, 0)
            st.dataframe(
                df_cc_tab.reset_index(drop=True),
                hide_index=True, use_container_width=True,
                column_config={
                    "CentroCusto":  st.column_config.TextColumn("Centro de Custo"),
                    "Realizado_QG": st.column_config.NumberColumn("Realizado", format="R$ %.2f"),
                    "%Total":       st.column_config.ProgressColumn("% do Total",
                                    format="%.1f%%", min_value=0, max_value=100),
                })

    # ══════════════════════════════════════════════════════════════════════════
    # ABA 4 — MRR VS CUSTO
    # ══════════════════════════════════════════════════════════════════════════
    with tab4:
        if df_mrr.empty:
            st.info("Aba MRR não encontrada ou sem dados.")
        else:
            df_mrr_f = df_mrr.copy()
            if ano!="Todos":
                df_mrr_f = df_mrr_f[df_mrr_f["Mes"].str.endswith(ano[2:])]
            merged = pd.merge(df_mrr_f, df_mes[["Mes","Realizado"]], on="Mes", how="inner")
            if merged.empty:
                st.info("Sem sobreposição de meses entre MRR e Budget.")
            else:
                merged["%Fac/MRR"] = np.where(
                    merged["MRR"]>0, merged["Realizado"]/merged["MRR"]*100, 0)
                k1,k2,k3 = st.columns(3)
                with k1: kpi("MRR Médio", brl(merged["MRR"].mean()))
                with k2: kpi("% Médio Facilities/MRR", f"{merged['%Fac/MRR'].mean():.2f}%")
                with k3: kpi("HC Médio", str(int(df_mrr_f["HC"].mean())))
                st.markdown("---")
                fig_m = fig_mrr(df_mrr_f, df_mes)
                if fig_m: st.plotly_chart(fig_m, use_container_width=True)
                st.dataframe(
                    merged[["Mes","MRR","Realizado","%Fac/MRR"]]
                      .sort_values("Mes",key=lambda s:s.map(mes_ord)).reset_index(drop=True),
                    hide_index=True, use_container_width=True,
                    column_config={
                        "Mes":       st.column_config.TextColumn("Mês"),
                        "MRR":       st.column_config.NumberColumn("MRR",       format="R$ %.2f"),
                        "Realizado": st.column_config.NumberColumn("Facilities", format="R$ %.2f"),
                        "%Fac/MRR":  st.column_config.ProgressColumn("% Custo/MRR",
                                     format="%.2f%%", min_value=0, max_value=10),
                    })

    # ══════════════════════════════════════════════════════════════════════════
    # ABA 5 — LANÇAMENTOS BRUTOS (Query Geral)
    # ══════════════════════════════════════════════════════════════════════════
    with tab5:
        st.markdown("##### Lançamentos Facilities — Query Geral (col N=Conta, O=Facilities, P=Centro)")
        if fq.empty:
            st.info("Nenhum lançamento Facilities para os filtros selecionados.")
        else:
            tot_v = fq["Valor"].sum()
            k1,k2,k3 = st.columns(3)
            with k1: kpi("Total Realizado", brl(tot_v))
            with k2: kpi("Lançamentos",     f"{len(fq):,}")
            with k3: kpi("Contas únicas",   str(fq["Conta"].nunique()))
            st.markdown("---")

            # Pivot: conta × mês
            if not fq.empty:
                pivot = (fq.groupby(["Conta","Mes"])["Valor"]
                           .sum().unstack(fill_value=0)
                           .reset_index())
                meses_p = sorted([c for c in pivot.columns if c!="Conta"], key=mes_ord)
                pivot = pivot[["Conta"]+meses_p]
                pivot["Total"] = pivot[meses_p].sum(axis=1)
                pivot = pivot.sort_values("Total",ascending=False)
                st.dataframe(pivot.reset_index(drop=True),
                             hide_index=True, use_container_width=True)

            st.markdown("---")
            st.markdown("##### Detalhe linha a linha")
            st.dataframe(
                fq[["Mes","Conta","CentroCusto","Valor"]]
                  .sort_values(["Mes","Valor"],ascending=[True,False]).reset_index(drop=True),
                hide_index=True, use_container_width=True,
                column_config={
                    "Mes":         st.column_config.TextColumn("Mês"),
                    "Conta":       st.column_config.TextColumn("Conta (col N)"),
                    "CentroCusto": st.column_config.TextColumn("Centro de Custo (col P)"),
                    "Valor":       st.column_config.NumberColumn("Realizado", format="R$ %.2f"),
                })

if __name__ == "__main__":
    main()
