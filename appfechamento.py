# appfechamento.py
import streamlit as st
import pandas as pd
import numpy as np
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import bcrypt
import re
from datetime import datetime
import html
import plotly.express as px
import plotly.graph_objects as go

# --- 1. CONFIGURAÇÕES E SEGURANÇA (APPSEC) ---
st.set_page_config(page_title="Portal Financeiro Corporativo", layout="wide", page_icon="🏢")

def verificar_senha(senha_fornecida: str, hash_armazenado: str) -> bool:
    try:
        return bcrypt.checkpw(senha_fornecida.encode('utf-8'), hash_armazenado.encode('utf-8'))
    except ValueError:
        return False

def sanitizar_input(texto: str) -> str:
    """Prevenção contra XSS e injeção de caracteres de controle."""
    if not isinstance(texto, str):
        return ""
    texto_limpo = html.escape(texto.strip())
    return re.sub(r'[\x00-\x1f\x7f-\x9f]', '', texto_limpo)

st.sidebar.title("🔒 Acesso Restrito")
senha_digitada = st.sidebar.text_input("Palavra-passe Corporativa:", type="password")

HASH_SENHA = st.secrets.get("senha_app_hash", "")
URL_BANCO_DADOS = st.secrets.get("url_planilha", "")

if not HASH_SENHA or not URL_BANCO_DADOS:
    st.error("🚨 Falha de Configuração Crítica: Secrets ausentes. Verifique as chaves no painel.")
    st.stop()

if not verificar_senha(senha_digitada, HASH_SENHA):
    st.warning("⚠️ Autenticação necessária.")
    st.stop()

st.sidebar.success("✅ Acesso Liberado")
st.sidebar.markdown("---")

# --- 2. CONEXÃO SEGURA COM GOOGLE SHEETS ---
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource(ttl=3600)
def get_google_client():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        return gspread.authorize(creds)
    except Exception as e:
        st.error("🚨 Erro Crítico na injeção de credenciais GCP.")
        st.stop()

# --- 3. MOTOR DE NORMALIZAÇÃO DE DADOS ---
def normalizar_valor(val) -> float:
    if pd.isna(val) or val == "": return 0.0
    if isinstance(val, (int, float)): return float(val)
    
    s = str(val).upper().replace("R$", "").strip()
    s = re.sub(r'[^\d.,-]', '', s)
    if not s or s == '-': return 0.0
    
    qtd_pontos = s.count('.')
    qtd_virgulas = s.count(',')
    
    if qtd_pontos == 1 and qtd_virgulas == 1:
        s = s.replace('.', '').replace(',', '.') if s.rfind(',') > s.rfind('.') else s.replace(',', '')
    elif qtd_pontos > 1 and qtd_virgulas <= 1: s = s.replace('.', '').replace(',', '.')
    elif qtd_virgulas > 1 and qtd_pontos <= 1: s = s.replace(',', '')
    elif qtd_pontos == 1 and qtd_virgulas == 0 and len(s.split('.')[-1]) == 3: s = s.replace('.', '')
    elif qtd_virgulas == 1 and qtd_pontos == 0:
        s = s.replace(',', '') if len(s.split(',')[-1]) == 3 else s.replace(',', '.')
        
    try: return float(s)
    except ValueError: return 0.0

def formatar_moeda(valor: float) -> str:
    if pd.isna(valor): return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

# --- 4. EXTRAÇÃO E TRATAMENTO (ETL) ---
@st.cache_data(ttl=600)
def carregar_dados_etl():
    client = get_google_client()
    sheet = client.open_by_url(URL_BANCO_DADOS)
    
    try:
        ws_lanc = sheet.worksheet("Query 2025").get_all_values()
        df_lanc = pd.DataFrame(ws_lanc[1:], columns=ws_lanc[0]) if len(ws_lanc) > 1 else pd.DataFrame()
        
        ws_budget = sheet.worksheet("Budget").get_all_values()
        df_budget = pd.DataFrame(ws_budget[1:], columns=ws_budget[0]) if len(ws_budget) > 1 else pd.DataFrame()
    except Exception as e:
        st.error(f"🚨 Erro de I/O no Google Sheets: {e}")
        return pd.DataFrame(), pd.DataFrame()

    if not df_lanc.empty:
        df_lanc.columns = [str(c).strip().upper() for c in df_lanc.columns]
        col_val_l = "DÉBITO/CRÉDITO (MC)" if "DÉBITO/CRÉDITO (MC)" in df_lanc.columns else df_lanc.columns[0]
        df_lanc["Realizado"] = df_lanc[col_val_l].apply(normalizar_valor)
        col_mes_l = next((c for c in df_lanc.columns if c in ['MÊS', 'MES', 'DATA']), None)
        df_lanc["Competência"] = pd.to_datetime(df_lanc[col_mes_l], errors='coerce').dt.strftime('%m/%Y').fillna("Sem Data") if col_mes_l else "Sem Data"
        df_lanc["Ano"] = df_lanc["Competência"].apply(lambda x: str(x).split('/')[-1] if '/' in str(x) else 'Sem Data')
        
        col_conta_l = next((c for c in df_lanc.columns if c in ['CTA.CONTÁB./CÓD.PN', 'CONTA', 'CONTA SAP']), None)
        df_lanc["CONTA"] = df_lanc[col_conta_l].astype(str).str.strip() if col_conta_l else "Sem Conta"
        df_lanc["Fornecedor"] = df_lanc.iloc[:, 11].astype(str).str.strip() if len(df_lanc.columns) >= 12 else "Sem Fornecedor"

    if not df_budget.empty:
        df_budget.columns = [str(c).strip().upper() for c in df_budget.columns]
        col_valor_b = next((c for c in df_budget.columns if c in ['BUDGET', 'ORÇADO', 'ORCAMENTO', 'VALOR']), None)
        df_budget["Orçado"] = df_budget[col_valor_b].apply(normalizar_valor) if col_valor_b else 0.0
        col_mes_b = next((c for c in df_budget.columns if c in ['MÊS', 'MES', 'DATA', 'COMPETÊNCIA', 'PERÍODO']), None)
        df_budget["Competência"] = pd.to_datetime(df_budget[col_mes_b], errors='coerce').dt.strftime('%m/%Y').fillna("Sem Data") if col_mes_b else "Sem Data"
        df_budget["Ano"] = df_budget["Competência"].apply(lambda x: str(x).split('/')[-1] if '/' in str(x) else 'Sem Data')
        
        col_conta_b = next((c for c in df_budget.columns if c in ['CONTA', 'CONTA SAP', 'CÓDIGO', 'CTA.CONTÁB./CÓD.PN']), None)
        df_budget["CONTA"] = df_budget[col_conta_b].astype(str).str.strip() if col_conta_b else "Sem Conta"
        df_budget["Nome da Conta"] = df_budget.iloc[:, 2].astype(str).str.strip() if len(df_budget.columns) >= 3 else df_budget["CONTA"]

    return df_lanc, df_budget

df_lanc, df_budget = carregar_dados_etl()

# --- 5. INTERFACE DO USUÁRIO ---
tab1, tab2 = st.tabs(["👔 Visão Executiva (CFO)", "📥 Inserir Lançamento"])

with tab1:
    if not df_lanc.empty or not df_budget.empty:
        st.markdown("### 🎛️ Motor de Filtros Analíticos")
        
        anos_disponiveis = sorted(list(set(df_lanc["Ano"].dropna().unique().tolist() + df_budget["Ano"].dropna().unique().tolist())), reverse=True)
        anos_disponiveis = [a for a in anos_disponiveis if a.isdigit()]
        if not anos_disponiveis: anos_disponiveis = [str(datetime.now().year)]

        col_f1, col_f2, col_f3, col_f4 = st.columns([1.5, 1, 1.5, 2])
        
        with col_f1:
            tipo_visao = st.radio("📊 Tipo de Análise:", ["Mensal", "Anual Consolidada"], horizontal=True)
            
        with col_f2:
            ano_alvo = st.selectbox("📅 Ano Base:", anos_disponiveis)
            
        with col_f3:
            if tipo_visao == "Mensal":
                meses_l = df_lanc[df_lanc["Ano"] == ano_alvo]["Competência"].unique().tolist()
                meses_b = df_budget[df_budget["Ano"] == ano_alvo]["Competência"].unique().tolist()
                meses_disp = sorted(list(set(meses_l + meses_b)))
                meses_disp = [m for m in meses_disp if '/' in m]
                mes_alvo = st.selectbox("📆 Mês Alvo:", meses_disp, index=len(meses_disp)-1 if meses_disp else 0)
            else:
                mes_alvo = "Todos"
                st.info(f"Visão Jan-Dez ({ano_alvo})")
                
        with col_f4:
            mrr_input = st.number_input(f"💰 Receita/MRR do Período ({'Mês' if tipo_visao == 'Mensal' else 'Ano'})", min_value=0.0, format="%.2f")

        st.markdown("---")
        
        # Lógica de Filtragem (Atual)
        def filtrar_periodo(ano, mes, visao):
            b = df_budget[df_budget["Competência"] == mes] if visao == "Mensal" else df_budget[df_budget["Ano"] == ano]
            l = df_lanc[df_lanc["Competência"] == mes] if visao == "Mensal" else df_lanc[df_lanc["Ano"] == ano]
            return b.copy(), l.copy()

        b_atual, l_atual = filtrar_periodo(ano_alvo, mes_alvo, tipo_visao)
        
        # Lógica de Filtragem (Período Anterior - Apenas para avaliar crescimento do Orçamento)
        b_prev, l_prev = pd.DataFrame(), pd.DataFrame()
        rotulo_comparativo = ""
        
        if tipo_visao == "Mensal" and 'meses_disp' in locals() and mes_alvo in meses_disp:
            idx = meses_disp.index(mes_alvo)
            if idx > 0:
                mes_prev = meses_disp[idx - 1]
                b_prev, _ = filtrar_periodo(ano_alvo, mes_prev, "Mensal")
                rotulo_comparativo = f"vs Budget Ant. ({mes_prev})"
        elif tipo_visao == "Anual Consolidada" and ano_alvo in anos_disponiveis:
            idx = anos_disponiveis.index(ano_alvo)
            if idx + 1 < len(anos_disponiveis):
                ano_prev = anos_disponiveis[idx + 1]
                b_prev, _ = filtrar_periodo(ano_prev, "Todos", "Anual Consolidada")
                rotulo_comparativo = f"vs Budget Ant. ({ano_prev})"

        # Agrupamento e Consolidação
        b_grp = b_atual.groupby(["CONTA", "Nome da Conta"])["Orçado"].sum().reset_index() if not b_atual.empty else pd.DataFrame(columns=["CONTA", "Nome da Conta", "Orçado"])
        l_grp = l_atual.groupby("CONTA")["Realizado"].sum().reset_index() if not l_atual.empty else pd.DataFrame(columns=["CONTA", "Realizado"])
        
        df_bi = pd.merge(b_grp, l_grp, on="CONTA", how="outer").fillna(0)
        df_bi = df_bi[(df_bi["Orçado"] != 0) | (df_bi["Realizado"] != 0)]
        df_bi["Nome da Conta"] = np.where(df_bi["Nome da Conta"] == 0, df_bi["CONTA"], df_bi["Nome da Conta"])
        df_bi["Saldo"] = df_bi["Orçado"] - df_bi["Realizado"]
        
        # Métricas Globais
        tot_orc = df_bi["Orçado"].sum()
        tot_real = df_bi["Realizado"].sum()
        
        pct_consumo_budget = (tot_real / tot_orc * 100) if tot_orc > 0 else 0.0
        lucro_op = mrr_input - tot_real
        margem_pct = (lucro_op / mrr_input * 100) if mrr_input > 0 else 0.0

        # --- NOVOS DELTAS ESTRATÉGICOS (Foco em aderência ao Budget) ---
        # 1. Delta dos Custos: Compara os Custos Realizados contra o Orçamento (Budget) do mesmo período
        if tot_orc > 0:
            var_custos_vs_budget = ((tot_real - tot_orc) / tot_orc) * 100
            delta_real_vs_orc = f"{var_custos_vs_budget:+.1f}% vs Orçamento"
        else:
            delta_real_vs_orc = None
            
        # 2. Delta do Orçamento: Avalia se a régua do Orçamento atual cresceu ou caiu em relação ao período anterior
        tot_orc_prev = b_prev["Orçado"].sum() if not b_prev.empty else 0.0
        delta_orc_pct = f"{((tot_orc - tot_orc_prev) / tot_orc_prev * 100):+.1f}% {rotulo_comparativo}" if tot_orc_prev > 0 else None

        # 3. Tratamento defensivo da Margem para o Streamlit (Evita seta fantasma)
        delta_lucro = f"{margem_pct:.1f}% de Margem" if mrr_input > 0 else None

        st.markdown("##### 💼 Demonstrativo de Resultados (P&L)")
        k1, k2, k3 = st.columns(3)
        k1.metric("Receita Declarada (MRR)", formatar_moeda(mrr_input))
        
        # Invertido: Custos abaixo do Budget = Verde (Economia). Acima = Vermelho (Estouro).
        k2.metric("Custos Totais Realizados", formatar_moeda(tot_real), delta=delta_real_vs_orc, delta_color="inverse")
        k3.metric("Lucro Operacional Estimado", formatar_moeda(lucro_op), delta=delta_lucro, delta_color="normal")

        st.markdown("##### 🎯 Consumo de Budget Global")
        b1, b2, b3 = st.columns(3)
        b1.metric("Orçamento Total (Budget)", formatar_moeda(tot_orc), delta=delta_orc_pct, delta_color="off")
        b2.metric("Saldo Disponível em Caixa", formatar_moeda(tot_orc - tot_real), "Estouro Identificado" if (tot_orc - tot_real) < 0 else "Dentro do Previsto", delta_color="normal")
        with b3:
            st.markdown(f"**Velocidade de Queima (Burn Rate):** `{pct_consumo_budget:.1f}%`")
            st.progress(min(pct_consumo_budget / 100, 1.0))

        st.markdown("---")
        
        linha1_col1, linha1_col2 = st.columns([3, 2])

        with linha1_col1:
            df_chart1 = df_bi.set_index("Nome da Conta")[["Orçado", "Realizado"]].sort_values("Realizado", ascending=False).head(10).reset_index()
            fig_vs = px.bar(
                df_chart1, x="Nome da Conta", y=["Orçado", "Realizado"], barmode="group",
                title="Orçamento vs Execução (Top 10 Contas)", color_discrete_map={"Orçado": "#1f77b4", "Realizado": "#ff7f0e"}
            )
            fig_vs.update_layout(xaxis_title="", yaxis_title="Valor (R$)", legend_title_text="", margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig_vs, use_container_width=True)

        with linha1_col2:
            fig_waterfall = go.Figure(go.Waterfall(
                name="P&L", orientation="v", measure=["relative", "relative", "total"],
                x=["Receita", "Custos", "Resultado"], textposition="outside",
                text=[f"R$ {mrr_input:,.0f}", f"R$ {-tot_real:,.0f}", f"R$ {lucro_op:,.0f}"],
                y=[mrr_input, -tot_real, lucro_op], connector={"line": {"color": "rgb(63, 63, 63)"}},
                decreasing={"marker": {"color": "#d62728"}}, increasing={"marker": {"color": "#2ca02c"}}, totals={"marker": {"color": "#1f77b4"}}
            ))
            fig_waterfall.update_layout(title="Formação do Resultado (Cash Burn)", margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig_waterfall, use_container_width=True)

        st.markdown("<br>", unsafe_allow_html=True)
        linha2_col1, linha2_col2 = st.columns(2)

        with linha2_col1:
            df_chart2 = df_bi.sort_values("Realizado", ascending=True).tail(7)
            fig_custos = px.bar(
                df_chart2, x="Realizado", y="Nome da Conta", orientation="h",
                title="Curva ABC: Maiores Ofensores de Caixa", color_discrete_sequence=["#d62728"], text_auto='.2s'
            )
            fig_custos.update_layout(xaxis_title="", yaxis_title="", margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig_custos, use_container_width=True)

        with linha2_col2:
            if not l_atual.empty and "Fornecedor" in l_atual.columns:
                df_forn = l_atual.groupby("Fornecedor")["Realizado"].sum().reset_index()
                df_chart3 = df_forn[df_forn["Realizado"] > 0].sort_values("Realizado", ascending=True).tail(7)
                fig_forn = px.bar(
                    df_chart3, x="Realizado", y="Fornecedor", orientation="h",
                    title="Concentração por Fornecedor (Top 7)", color_discrete_sequence=["#2ca02c"], text_auto='.2s'
                )
                fig_forn.update_layout(xaxis_title="", yaxis_title="", margin=dict(t=40, b=0, l=0, r=0))
                st.plotly_chart(fig_forn, use_container_width=True)

        st.markdown("---")
        st.markdown("##### 📋 Matriz de Custos")
        df_bi["% Uso do Budget"] = np.where(df_bi["Orçado"] > 0, (df_bi["Realizado"] / df_bi["Orçado"]) * 100, np.where(df_bi["Realizado"] > 0, 100.0, 0))
        df_bi["% Consumo da Receita"] = np.where(mrr_input > 0, (df_bi["Realizado"] / mrr_input) * 100, 0)
        df_bi["Status"] = np.where(df_bi["Realizado"] > df_bi["Orçado"], "🔴 Estourou", np.where(df_bi["Realizado"] >= df_bi["Orçado"] * 0.85, "🟡 Alerta", "🟢 OK"))
        df_bi["Status"] = np.where((df_bi["Orçado"] == 0) & (df_bi["Realizado"] == 0), "⚪ Sem Movimento", df_bi["Status"])
        
        st.dataframe(
            df_bi[["Status", "Nome da Conta", "Orçado", "Realizado", "Saldo", "% Uso do Budget", "% Consumo da Receita"]].sort_values("Realizado", ascending=False),
            column_config={
                "Status": st.column_config.TextColumn("Alerta"),
                "Nome da Conta": st.column_config.TextColumn("Conta (Budget)"),
                "Orçado": st.column_config.NumberColumn("Budget", format="R$ %.2f"),
                "Realizado": st.column_config.NumberColumn("Realizado", format="R$ %.2f"),
                "Saldo": st.column_config.NumberColumn("Saldo", format="R$ %.2f"),
                "% Uso do Budget": st.column_config.ProgressColumn("🔥 Consumo", format="%.1f%%", min_value=0, max_value=100),
                "% Consumo da Receita": st.column_config.ProgressColumn("Peso Receita", format="%.2f%%", min_value=0, max_value=100)
            }, hide_index=True, use_container_width=True
        )

with tab2:
    st.markdown("### Lançamento Unitário no ERP")
    with st.form("form_novo_lancamento", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            data_mes = st.date_input("Mês da Competência *")
            conta_sap = st.text_input("Cta.contáb./cód.PN *", max_chars=50)
            fornecedor = st.text_input("Fornecedor *", max_chars=100)
        with c2:
            centro_custo = st.text_input("Centro de Custo", max_chars=50)
            valor_deb_cred = st.number_input("Débito/crédito (MC) (R$) *", format="%.2f")
            observacoes = st.text_input("Observações", max_chars=255)

        submit = st.form_submit_button("🚀 Inserir Linha", use_container_width=True)

    if submit:
        conta_sap_san = sanitizar_input(conta_sap)
        fornecedor_san = sanitizar_input(fornecedor)
        
        if not conta_sap_san or not fornecedor_san:
            st.error("🚨 Entradas inválidas ou campos obrigatórios ausentes.")
        else:
            with st.spinner("Persistindo dados..."):
                try:
                    client = get_google_client()
                    sheet = client.open_by_url(URL_BANCO_DADOS)
                    worksheet = sheet.worksheet("Query 2025")
                    cabecalhos = worksheet.row_values(1)
                    
                    dados_insert = {
                        "Mês": data_mes.strftime("%Y-%m-%d"),
                        "Cta.contáb./cód.PN": conta_sap_san,
                        "Débito/crédito (MC)": str(valor_deb_cred).replace(".", ","),
                        "Observações": sanitizar_input(observacoes),
                        "Fornecedor": fornecedor_san,
                        "Centro de Custo": sanitizar_input(centro_custo),
                        "FORNECEDOR": fornecedor_san,
                        "Cta.contáb./cód.PN 2": conta_sap_san,
                        "Conta Contabil": conta_sap_san
                    }
                    
                    nova_linha = [dados_insert.get(col, "") for col in cabecalhos]
                    worksheet.append_row(nova_linha)
                    st.success("✅ Lançamento auditado e inserido com sucesso.")
                    carregar_dados_etl.clear() 
                except Exception as e:
                    st.error(f"🚨 Falha na transação DML: {e}")
