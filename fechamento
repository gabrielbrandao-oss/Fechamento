import streamlit as st
import pandas as pd
import numpy as np
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURAÇÕES DA PLATAFORMA ---
st.set_page_config(page_title="Portal Financeiro BI", layout="wide", page_icon="🏢")

# --- SISTEMA DE ACESSO ---
st.sidebar.title("🔒 Acesso Restrito")
senha_digitada = st.sidebar.text_input("Senha Corporativa:", type="password")

SENHA_CORRETA = st.secrets.get("senha_app", "admin123")
URL_PLANILHA = st.secrets.get("url_planilha", "")

if senha_digitada != SENHA_CORRETA:
    st.warning("Aguardando autenticação para carregar os dados...")
    st.stop()

st.sidebar.success("Acesso Liberado")
st.sidebar.markdown("---")

# --- CONEXÃO GOOGLE SHEETS ---
@st.cache_resource
def get_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
    return gspread.authorize(creds)

# --- MOTOR DE LIMPEZA FINANCEIRA ---
def limpar_financeiro(val):
    if pd.isna(val) or val == "": return 0.0
    if isinstance(val, (int, float)): return float(val)
    s = str(val).upper().replace("R$", "").strip()
    s = ''.join(c for c in s if c.isdigit() or c in '.,-')
    if not s or s == '-': return 0.0
    if s.count('.') >= 1 and s.count(',') == 1: # Padrão BR 1.000,00
        s = s.replace('.', '').replace(',', '.')
    elif s.count(',') == 1 and s.count('.') == 0: # Padrão 1000,00
        s = s.replace(',', '.')
    try: return float(s)
    except: return 0.0

def formatar_br(n):
    return f"R$ {n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- CARREGAMENTO DE DADOS (ETL) ---
try:
    client = get_client()
    sh = client.open_by_url(URL_PLANILHA)
    
    # Lançamentos
    data_l = sh.worksheet("Lancamentos").get_all_values()
    df_l = pd.DataFrame(data_l[1:], columns=data_l[0])
    
    # Budget
    data_b = sh.worksheet("Budget").get_all_values()
    df_b = pd.DataFrame(data_b[1:], columns=data_b[0])

    # Normalização
    df_l["Valor"] = df_l["Débito/crédito (MC)"].apply(limper_financeiro)
    df_l["Competência"] = pd.to_datetime(df_l["Mês"], errors='coerce').dt.strftime('%m/%Y')
    
    df_b["Valor_B"] = df_b["BUDGET"].apply(limper_financeiro)
    df_b["Competência"] = pd.to_datetime(df_b["MÊS"], dayfirst=True, errors='coerce').dt.strftime('%m/%Y')
    
except Exception as e:
    st.error(f"Erro na conexão com os dados: {e}")
    st.stop()

# --- INTERFACE ---
tab1, tab2 = st.tabs(["👔 Dashboard CFO", "📥 Novo Lançamento"])

with tab1:
    st.subheader("Performance Financeira")
    
    # Filtros
    c1, c2 = st.columns([1, 2])
    meses = sorted(df_b["Competência"].unique().tolist())
    with c1:
        mes_sel = st.selectbox("Selecione o Mês:", meses, index=len(meses)-1)
    with c2:
        mrr = st.number_input("Receita Mensal (MRR) R$:", min_value=0.0, format="%.2f")

    # Cálculos
    b_mes = df_b[df_b["Competência"] == mes_sel]
    l_mes = df_l[df_l["Competência"] == mes_sel]
    l_grp = l_mes.groupby("Cta.contáb./cód.PN")["Valor"].sum().reset_index()
    
    df_final = pd.merge(b_mes, l_grp, left_on="CONTA", right_on="Cta.contáb./cód.PN", how="left").fillna(0)
    
    tot_orc = df_final["Valor_B"].sum()
    tot_real = df_final["Valor"].sum()
    
    # KPIs
    k1, k2, k3 = st.columns(3)
    k1.metric("Receita Total", formatar_br(mrr))
    k2.metric("Custos Totais", formatar_moeda_br(tot_real))
    if mrr > 0:
        margem = ((mrr - tot_real) / mrr) * 100
        k3.metric("Margem Operacional", f"{margem:.1f}%", delta=f"{mrr-tot_real:,.2f}")

    st.divider()
    
    # Tabela Gerencial
    st.markdown("### Detalhamento por Conta")
    df_final["% Rec"] = (df_final["Valor"] / mrr * 100) if mrr > 0 else 0
    df_final["Saldo"] = df_final["Valor_B"] - df_final["Valor"]
    
    st.dataframe(
        df_final[["CONTA", "TIPO 1", "Valor_B", "Valor", "Saldo", "% Rec"]],
        column_config={
            "CONTA": "Conta SAP",
            "Valor_B": st.column_config.NumberColumn("Budget", format="R$ %.2f"),
            "Valor": st.column_config.NumberColumn("Realizado", format="R$ %.2f"),
            "Saldo": st.column_config.NumberColumn("Saldo", format="R$ %.2f"),
            "% Rec": st.column_config.ProgressColumn("% s/ Receita", format="%.2f%%", min_value=0, max_value=20)
        },
        use_container_width=True, hide_index=True
    )

with tab2:
    st.subheader("Inserir Dado Manual")
    with st.form("f1", clear_on_submit=True):
        c1, c2 = st.columns(2)
        m = c1.date_input("Mês da Competência")
        cta = c1.text_input("Conta SAP")
        forn = c2.text_input("Fornecedor")
        val = c2.number_input("Valor R$", format="%.2f")
        obs = st.text_area("Observações")
        if st.form_submit_button("Gravar na Planilha"):
            # Lógica de gravação simples
            try:
                sh.worksheet("Lancamentos").append_row([m.strftime("%Y-%m-%d"), cta, "", "", val, obs, forn])
                st.success("Gravado!")
            except:
                st.error("Erro ao gravar")
