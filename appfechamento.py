import streamlit as st
import pandas as pd
import numpy as np
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 1. CONFIGURAÇÕES DO PORTAL E SEGURANÇA ---
st.set_page_config(page_title="Portal Financeiro Corporativo", layout="wide", page_icon="🏢")

st.sidebar.title("🔒 Acesso Restrito")
senha_digitada = st.sidebar.text_input("Palavra-passe Corporativa:", type="password")

# Credenciais e Variáveis de Ambiente (Secrets)
SENHA_CORRETA = st.secrets.get("senha_app", "admin123") 
URL_BANCO_DADOS = st.secrets.get("url_planilha", "")

if senha_digitada != SENHA_CORRETA:
    st.warning("⚠️ Insira a palavra-passe corporativa no menu lateral para aceder à plataforma.")
    st.stop()

st.sidebar.success("✅ Acesso Liberado!")
st.sidebar.markdown("---")

# --- 2. CONEXÃO COM O GOOGLE SHEETS ---
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def get_google_client():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        return gspread.authorize(creds)
    except KeyError:
        st.error("⚠️ Credenciais do Google não encontradas nos Secrets.")
        st.stop()

# --- 3. MOTOR DE NORMALIZAÇÃO DE DADOS ---
def normalizar_valor(val):
    if pd.isna(val) or val == "": return 0.0
    if isinstance(val, (int, float)): return float(val)
    
    s = str(val).upper().replace("R$", "").strip()
    s = ''.join(c for c in s if c.isdigit() or c in '.,-') 
    if not s or s == '-': return 0.0
    
    qtd_pontos = s.count('.')
    qtd_virgulas = s.count(',')
    
    if qtd_pontos == 1 and qtd_virgulas == 1:
        if s.rfind(',') > s.rfind('.'): s = s.replace('.', '').replace(',', '.')
        else: s = s.replace(',', '') 
    elif qtd_pontos > 1 and qtd_virgulas <= 1: s = s.replace('.', '').replace(',', '.') 
    elif qtd_virgulas > 1 and qtd_pontos <= 1: s = s.replace(',', '') 
    elif qtd_pontos == 1 and qtd_virgulas == 0:
        if len(s.split('.')[-1]) == 3: s = s.replace('.', '') 
    elif qtd_virgulas == 1 and qtd_pontos == 0:
        if len(s.split(',')[-1]) == 3: s = s.replace(',', '') 
        else: s = s.replace(',', '.') 
        
    try: return float(s)
    except: return 0.0

def formatar_moeda(valor):
    try:
        if pd.isna(valor): return "R$ 0,00"
        txt = f"{float(valor):,.2f}"
        return f"R$ {txt.replace(',', 'X').replace('.', ',').replace('X', '.')}"
    except: return "R$ 0,00"

# --- 4. EXTRAÇÃO DE DADOS (ETL) ---
if not URL_BANCO_DADOS:
    st.error("⚠️ Configure a 'url_planilha' no painel de Secrets.")
    st.stop()

try:
    client = get_google_client()
    sheet = client.open_by_url(URL_BANCO_DADOS)
    
    # Aba Query 2025
    ws_lanc = sheet.worksheet("Query 2025").get_all_values()
    df_lanc = pd.DataFrame(ws_lanc[1:], columns=ws_lanc[0]) if ws_lanc and len(ws_lanc) > 1 else pd.DataFrame()
        
    # Aba Budget
    ws_budget = sheet.worksheet("Budget").get_all_values()
    df_budget = pd.DataFrame(ws_budget[1:], columns=ws_budget[0]) if ws_budget and len(ws_budget) > 1 else pd.DataFrame()
    
    # Tratamento Lançamentos
    if not df_lanc.empty:
        colunas_upper_l = [str(c).strip().upper() for c in df_lanc.columns]
        
        # Encontra coluna de Valor
        col_val_l = df_lanc.columns[colunas_upper_l.index("DÉBITO/CRÉDITO (MC)")] if "DÉBITO/CRÉDITO (MC)" in colunas_upper_l else df_lanc.columns[0]
        df_lanc["Realizado"] = df_lanc[col_val_l].apply(normalizar_valor)
        
        # Encontra coluna de Mês
        col_mes_l = next((c for c, c_up in zip(df_lanc.columns, colunas_upper_l) if c_up in ['MÊS', 'MES', 'DATA']), None)
        if col_mes_l:
            df_lanc["Data_Temp"] = pd.to_datetime(df_lanc[col_mes_l], errors='coerce')
            df_lanc["Competência"] = df_lanc["Data_Temp"].dt.strftime('%m/%Y').fillna(df_lanc[col_mes_l].astype(str).str.strip())
        else:
            df_lanc["Competência"] = "Sem Data"
            
        # Encontra coluna de Conta (Código)
        col_conta_l = next((c for c, c_up in zip(df_lanc.columns, colunas_upper_l) if c_up in ['CTA.CONTÁB./CÓD.PN', 'CONTA', 'CONTA SAP']), None)
        df_lanc["CONTA"] = df_lanc[col_conta_l].astype(str).str.strip() if col_conta_l else "Sem Conta"

        # Encontra coluna de Nome da Conta (NOVIDADE)
        col_nome_l = next((c for c, c_up in zip(df_lanc.columns, colunas_upper_l) if c_up in ['CTA.CONT./NOME PN', 'NOME DA CONTA', 'DESCRIÇÃO']), None)
        df_lanc["Nome da Conta"] = df_lanc[col_nome_l].astype(str).str.strip() if col_nome_l else df_lanc["CONTA"]

    # Tratamento Budget (Busca Inteligente)
    if not df_budget.empty:
        colunas_upper_b = [str(c).strip().upper() for c in df_budget.columns]
        
        col_valor_b = next((c for c, c_up in zip(df_budget.columns, colunas_upper_b) if c_up in ['BUDGET', 'ORÇADO', 'ORCAMENTO', 'VALOR']), None)
        df_budget["Orçado"] = df_budget[col_valor_b].apply(normalizar_valor) if col_valor_b else 0.0
        
        col_mes_b = next((c for c, c_up in zip(df_budget.columns, colunas_upper_b) if c_up in ['MÊS', 'MES', 'DATA', 'COMPETÊNCIA', 'PERÍODO']), None)
        if col_mes_b:
            df_budget["Data_Temp"] = pd.to_datetime(df_budget[col_mes_b], errors='coerce')
            df_budget["Competência"] = df_budget["Data_Temp"].dt.strftime('%m/%Y').fillna(df_budget[col_mes_b].astype(str).str.strip())
        else:
            df_budget["Competência"] = "Sem Data"
            
        col_conta_b = next((c for c, c_up in zip(df_budget.columns, colunas_upper_b) if c_up in ['CONTA', 'CONTA SAP', 'CÓDIGO', 'CTA.CONTÁB./CÓD.PN']), None)
        df_budget["CONTA"] = df_budget[col_conta_b].astype(str).str.strip() if col_conta_b else "Sem Conta"

except Exception as e:
    st.error(f"Falha ao conectar com a Planilha. Erro: {e}")
    df_lanc, df_budget = pd.DataFrame(), pd.DataFrame()

# --- 5. INTERFACE DO UTILIZADOR (TABS) ---
tab1, tab2 = st.tabs(["👔 Visão Executiva (CFO)", "📥 Inserir Lançamento"])

# ==========================================
# MÓDULO A: DASHBOARD EXECUTIVO
# ==========================================
with tab1:
    if not df_lanc.empty or not df_budget.empty:
        st.markdown("### 🎛️ Parâmetros do Painel")
        col_f1, col_f2 = st.columns([1, 2])
        
        meses_lanc = df_lanc["Competência"].dropna().unique().tolist() if not df_lanc.empty else []
        meses_bud = df_budget["Competência"].dropna().unique().tolist() if not df_budget.empty else []
        
        meses_dash = sorted(list(set(meses_lanc + meses_bud)))
        meses_dash = [m for m in meses_dash if m != 'NaT' and str(m).strip() not in ['nan', '', 'Sem Data']]
        
        with col_f1:
            mes_alvo = st.selectbox("📅 Competência:", meses_dash, index=len(meses_dash)-1 if meses_dash else 0)
        with col_f2:
            mrr_input = st.number_input("💰 Receita/MRR do Mês (R$)", min_value=0.0, format="%.2f", help="Insira a faturação para calcular margens.")
        
        st.markdown("---")
        
        # Cruzamento de Dados (Matching)
        b_mes = df_budget[df_budget["Competência"] == mes_alvo].copy() if not df_budget.empty else pd.DataFrame(columns=["CONTA", "Orçado"])
        l_mes = df_lanc[df_lanc["Competência"] == mes_alvo].copy() if not df_lanc.empty else pd.DataFrame(columns=["CONTA", "Realizado", "Nome da Conta"])
        
        b_grp = b_mes.groupby("CONTA")["Orçado"].sum().reset_index() if not b_mes.empty else pd.DataFrame(columns=["CONTA", "Orçado"])
        l_grp = l_mes.groupby("CONTA")["Realizado"].sum().reset_index() if not l_mes.empty else pd.DataFrame(columns=["CONTA", "Realizado"])
        
        df_bi = pd.merge(b_grp, l_grp, on="CONTA", how="outer").fillna(0)
        
        # O TRADUTOR DE NOMES (De Código SAP para Nome da Conta)
        if not df_lanc.empty:
            dict_nomes = df_lanc.drop_duplicates("CONTA").set_index("CONTA")["Nome da Conta"].to_dict()
            df_bi["Nome da Conta"] = df_bi["CONTA"].map(dict_nomes).fillna(df_bi["CONTA"])
            df_bi["Nome da Conta"] = np.where(df_bi["Nome da Conta"] == "", df_bi["CONTA"], df_bi["Nome da Conta"])
        else:
            df_bi["Nome da Conta"] = df_bi["CONTA"]

        df_bi["Saldo"] = df_bi["Orçado"] - df_bi["Realizado"]
        
        tot_orc = df_bi["Orçado"].sum()
        tot_real = df_bi["Realizado"].sum()
        
        # KPIs
        pct_consumo_budget = (tot_real / tot_orc * 100) if tot_orc > 0 else 0
        lucro_op = mrr_input - tot_real
        margem_pct = (lucro_op / mrr_input * 100) if mrr_input > 0 else 0

        # Linha 1: Receita
        st.markdown("##### 💼 Demonstrativo de Resultados (P&L)")
        k1, k2, k3 = st.columns(3)
        k1.metric("Receita (MRR)", formatar_moeda(mrr_input))
        k2.metric("Custos (Realizado)", formatar_moeda(tot_real))
        if mrr_input > 0:
            k3.metric("Lucro Operacional", formatar_moeda(lucro_op), f"{margem_pct:.1f}% de Margem", delta_color="normal")
        else:
            k3.metric("Lucro Operacional", "---")

        st.markdown("<br>", unsafe_allow_html=True)

        # Linha 2: Budget
        st.markdown("##### 🎯 Consumo de Budget")
        b1, b2, b3 = st.columns(3)
        b1.metric("Orçamento Total", formatar_moeda(tot_orc))
        b2.metric("Saldo Disponível", formatar_moeda(tot_orc - tot_real), "Estouro" if (tot_orc - tot_real) < 0 else "OK", delta_color="normal")
        with b3:
            st.markdown(f"**Progresso:** `{pct_consumo_budget:.1f}%`")
            st.progress(min(pct_consumo_budget / 100, 1.0))

        st.markdown("---")

        # Gráficos COM OS NOMES DAS CONTAS
        col_g1, col_g2 = st.columns([2, 1])
        with col_g1:
            st.markdown("##### 📊 Realizado vs Orçado (Por Conta)")
            df_chart = df_bi.set_index("Nome da Conta")[["Orçado", "Realizado"]].sort_values("Realizado", ascending=False).head(10)
            if not df_chart.empty: st.bar_chart(df_chart, color=["#1f77b4", "#ff7f0e"])
        with col_g2:
            st.markdown("##### 💸 Maiores Custos")
            if not df_bi.empty: st.bar_chart(df_bi.sort_values("Realizado", ascending=False).head(5).set_index("Nome da Conta")["Realizado"], color="#d62728")

        st.markdown("---")

        # Tabela Gerencial COM OS NOMES DAS CONTAS
        st.markdown("##### 📋 Matriz de Custos")
        df_bi["% Consumo da Receita"] = np.where(mrr_input > 0, (df_bi["Realizado"] / mrr_input) * 100, 0)
        
        st.dataframe(
            df_bi[["Nome da Conta", "Orçado", "Realizado", "Saldo", "% Consumo da Receita"]],
            column_config={
                "Nome da Conta": st.column_config.TextColumn("Conta / Descrição"),
                "Orçado": st.column_config.NumberColumn("Budget", format="R$ %.2f"),
                "Realizado": st.column_config.NumberColumn("Realizado", format="R$ %.2f"),
                "Saldo": st.column_config.NumberColumn("Saldo", format="R$ %.2f"),
                "% Consumo da Receita": st.column_config.ProgressColumn("Peso na Receita", format="%.2f%%", min_value=0, max_value=100)
            },
            hide_index=True, use_container_width=True
        )

# ==========================================
# MÓDULO B: INGESTÃO MANUAL
# ==========================================
with tab2:
    st.markdown("### Lançamento Unitário no ERP (Query 2025)")
    st.caption("Ao preencher, o sistema preencherá automaticamente as colunas da folha.")
    
    with st.form("form_novo_lancamento", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            data_mes = st.date_input("Mês da Competência *")
            conta_sap = st.text_input("Cta.contáb./cód.PN (Ex: 4.1.02.01.0002) *")
            nome_conta = st.text_input("Nome da Conta (Cta.cont./Nome PN)")
            fornecedor = st.text_input("Fornecedor *")
        with c2:
            centro_custo = st.text_input("Centro de Custo")
            valor_deb_cred = st.number_input("Débito/crédito (MC) (R$) *", format="%.2f")
            observacoes = st.text_input("Observações")

        submit = st.form_submit_button("🚀 Inserir Linha na Folha", use_container_width=True)

    if submit:
        if not conta_sap or not fornecedor:
            st.error("❌ Preencha os campos obrigatórios (*).")
        else:
            with st.spinner("A guardar no Banco de Dados..."):
                try:
                    worksheet = sheet.worksheet("Query 2025")
                    cabecalhos = worksheet.row_values(1)
                    nova_linha = [""] * len(cabecalhos)
                    
                    dados_insert = {
                        "Mês": data_mes.strftime("%Y-%m-%d"),
                        "Cta.contáb./cód.PN": conta_sap,
                        "Cta.cont./Nome PN": nome_conta,
                        "Débito/crédito (MC)": str(valor_deb_cred).replace(".", ","),
                        "Observações": observacoes,
                        "Fornecedor": fornecedor,
                        "Centro de Custo": centro_custo,
                        "Diretoria": "",
                        "Natureza": "",
                        "Pacote": "",
                        "FORNECEDOR": fornecedor,
                        "Cta.contáb./cód.PN 2": conta_sap,
                        "Conta Contabil": conta_sap
                    }
                    
                    for col_nome, valor in dados_insert.items():
                        if col_nome in cabecalhos: nova_linha[cabecalhos.index(col_nome)] = valor
                            
                    worksheet.append_row(nova_linha)
                    st.success("✅ Lançamento inserido com sucesso na base de dados!")
                except Exception as e:
                    st.error(f"Erro de conexão: {e}")
