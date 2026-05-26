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
    if not isinstance(texto, str): return ""
    return re.sub(r'[\x00-\x1f\x7f-\x9f]', '', html.escape(texto.strip()))

st.sidebar.title("🔒 Acesso Restrito")
senha_digitada = st.sidebar.text_input("Palavra-passe Corporativa:", type="password")

HASH_SENHA = st.secrets.get("senha_app_hash", "")
URL_BANCO_DADOS = st.secrets.get("url_planilha", "")

if not HASH_SENHA or not URL_BANCO_DADOS:
    st.error("🚨 Falha Crítica: Secrets ausentes (senha_app_hash ou url_planilha).")
    st.stop()

if not verificar_senha(senha_digitada, HASH_SENHA):
    st.warning("⚠️ Autenticação necessária.")
    st.stop()

st.sidebar.success("✅ Acesso Liberado")
st.sidebar.markdown("---")

# --- 2. CONEXÃO COM GOOGLE SHEETS ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

@st.cache_resource(ttl=3600)
def get_google_client():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        return gspread.authorize(creds)
    except Exception as e:
        st.error("🚨 Erro na injeção de credenciais GCP.")
        st.stop()

# --- 3. MOTOR DE NORMALIZAÇÃO ---
def normalizar_valor(val) -> float:
    if pd.isna(val) or val == "": return 0.0
    if isinstance(val, (int, float)): return float(val)
    s = str(val).upper().replace("R$", "").strip()
    s = re.sub(r'[^\d.,-]', '', s)
    if not s or s == '-': return 0.0
    qtd_p, qtd_v = s.count('.'), s.count(',')
    if qtd_p == 1 and qtd_v == 1: s = s.replace('.', '').replace(',', '.') if s.rfind(',') > s.rfind('.') else s.replace(',', '')
    elif qtd_p > 1 and qtd_v <= 1: s = s.replace('.', '').replace(',', '.')
    elif qtd_v > 1 and qtd_p <= 1: s = s.replace(',', '')
    elif qtd_p == 1 and qtd_v == 0 and len(s.split('.')[-1]) == 3: s = s.replace('.', '')
    elif qtd_v == 1 and qtd_p == 0: s = s.replace(',', '') if len(s.split(',')[-1]) == 3 else s.replace(',', '.')
    try: return float(s)
    except ValueError: return 0.0

def formatar_moeda(valor: float) -> str:
    if pd.isna(valor): return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

# --- 4. EXTRAÇÃO ETL (CACHE V6 - ISOLAMENTO DRILL-DOWN) ---
@st.cache_data(ttl=600)
def extrair_dados_nuvem_v6():
    client = get_google_client()
    sheet = client.open_by_url(URL_BANCO_DADOS)
    try:
        ws_lanc = sheet.worksheet("Query 2025").get_all_values()
        df_lanc = pd.DataFrame(ws_lanc[1:], columns=ws_lanc[0]) if len(ws_lanc) > 1 else pd.DataFrame()
        ws_budget = sheet.worksheet("Budget").get_all_values()
        df_budget = pd.DataFrame(ws_budget[1:], columns=ws_budget[0]) if len(ws_budget) > 1 else pd.DataFrame()
    except Exception as e:
        st.error(f"🚨 Erro de I/O: {e}")
        return pd.DataFrame(), pd.DataFrame()

    if not df_lanc.empty:
        df_lanc.columns = [str(c).strip().upper() for c in df_lanc.columns]
        col_val_l = "DÉBITO/CRÉDITO (MC)" if "DÉBITO/CRÉDITO (MC)" in df_lanc.columns else df_lanc.columns[0]
        df_lanc["Realizado"] = df_lanc[col_val_l].apply(normalizar_valor)
        col_mes_l = next((c for c in df_lanc.columns if c in ['MÊS', 'MES', 'DATA']), None)
        if col_mes_l:
            data_temp = pd.to_datetime(df_lanc[col_mes_l], errors='coerce')
            df_lanc["Competência"] = data_temp.dt.strftime('%m/%Y').fillna(df_lanc[col_mes_l].astype(str).str.strip())
        else:
            df_lanc["Competência"] = "Sem Data"
        df_lanc["Ano"] = df_lanc["Competência"].apply(lambda x: str(x).split('/')[-1] if '/' in str(x) else str(x))
        col_conta_l = next((c for c in df_lanc.columns if c in ['CTA.CONTÁB./CÓD.PN', 'CONTA', 'CONTA SAP']), None)
        df_lanc["CONTA"] = df_lanc[col_conta_l].astype(str).str.strip() if col_conta_l else "Sem Conta"
        df_lanc["Fornecedor"] = df_lanc.iloc[:, 11].astype(str).str.strip() if len(df_lanc.columns) >= 12 else "Sem Fornecedor"

    if not df_budget.empty:
        df_budget.columns = [str(c).strip().upper() for c in df_budget.columns]
        col_valor_b = next((c for c in df_budget.columns if c in ['BUDGET', 'ORÇADO', 'ORCAMENTO', 'VALOR']), None)
        df_budget["Orçado"] = df_budget[col_valor_b].apply(normalizar_valor) if col_valor_b else 0.0
        col_mes_b = next((c for c in df_budget.columns if c in ['MÊS', 'MES', 'DATA', 'COMPETÊNCIA', 'PERÍODO']), None)
        if col_mes_b:
            data_temp = pd.to_datetime(df_budget[col_mes_b], errors='coerce')
            df_budget["Competência"] = data_temp.dt.strftime('%m/%Y').fillna(df_budget[col_mes_b].astype(str).str.strip())
        else:
            df_budget["Competência"] = "Sem Data"
        df_budget["Ano"] = df_budget["Competência"].apply(lambda x: str(x).split('/')[-1] if '/' in str(x) else str(x))
        col_conta_b = next((c for c in df_budget.columns if c in ['CONTA', 'CONTA SAP', 'CÓDIGO', 'CTA.CONTÁB./CÓD.PN']), None)
        df_budget["CONTA"] = df_budget[col_conta_b].astype(str).str.strip() if col_conta_b else "Sem Conta"
        df_budget["Nome da Conta"] = df_budget.iloc[:, 2].astype(str).str.strip() if len(df_budget.columns) >= 3 else df_budget["CONTA"]

    return df_lanc, df_budget

df_lanc, df_budget = extrair_dados_nuvem_v6()

# --- 5. INTERFACE DO USUÁRIO ---
tab1, tab2 = st.tabs(["👔 Visão Executiva (CFO)", "📥 Inserir Lançamento"])

with tab1:
    if not df_lanc.empty or not df_budget.empty:
        st.markdown("### 🎛️ Motor de Filtros Analíticos")
        
        anos_disponiveis = sorted(list(set(df_budget["Ano"].dropna().astype(str).tolist())), reverse=True)
        anos_disponiveis = [a for a in anos_disponiveis if a.isdigit()]
        if not anos_disponiveis: anos_disponiveis = [str(datetime.now().year)]

        col_f1, col_f2, col_f3, col_f4 = st.columns([1.5, 1, 1.5, 2])
        
        with col_f1:
            tipo_visao = st.radio("📊 Tipo de Análise:", ["Mensal", "Anual Consolidada"], horizontal=True)
            
        with col_f2:
            ano_alvo = st.selectbox("📅 Ano Base:", anos_disponiveis)
            
        with col_f3:
            if tipo_visao == "Mensal":
                meses_disp = sorted(list(set(df_budget[df_budget["Ano"] == ano_alvo]["Competência"].dropna().tolist())))
                meses_disp = [m for m in meses_disp if '/' in str(m)]
                mes_alvo = st.selectbox("📆 Mês Alvo:", meses_disp, index=len(meses_disp)-1 if meses_disp else 0)
            else:
                mes_alvo = "Todos"
                st.info(f"Visão Consolidada ({ano_alvo})")
                
        with col_f4:
            mrr_input = st.number_input(f"💰 Receita Manual (Opcional)", min_value=0.0, format="%.2f")

        st.markdown("---")
        
        def filtrar_periodo(ano, mes, visao):
            b = df_budget[df_budget["Competência"] == mes] if visao == "Mensal" else df_budget[df_budget["Ano"] == ano]
            l = df_lanc[df_lanc["Competência"] == mes] if visao == "Mensal" else df_lanc[df_lanc["Ano"] == ano]
            return b.copy(), l.copy()

        b_atual, l_atual = filtrar_periodo(ano_alvo, mes_alvo, tipo_visao)
        b_prev = pd.DataFrame()
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

        # KPIs (Isolados do Budget)
        tot_orc_kpi = b_atual["Orçado"].sum()
        col_real_budget = next((c for c in b_atual.columns if "REALIZADO" in c or "EXECUTADO" in c), None)
        if col_real_budget:
            b_atual[col_real_budget] = b_atual[col_real_budget].apply(normalizar_valor)
            tot_real_kpi = b_atual[col_real_budget].sum()
            if tot_real_kpi == 0: tot_real_kpi = l_atual["Realizado"].sum()
        else:
            tot_real_kpi = l_atual["Realizado"].sum()
            
        col_rec_budget = next((c for c in b_atual.columns if "RECEITA" in c or "MRR" in c or "FATURAMENTO" in c), None)
        if col_rec_budget:
            b_atual[col_rec_budget] = b_atual[col_rec_budget].apply(normalizar_valor)
            mrr_val = b_atual[col_rec_budget].sum()
            if mrr_val == 0: mrr_val = mrr_input
        else:
            mrr_val = mrr_input

        pct_consumo_budget = (tot_real_kpi / tot_orc_kpi * 100) if tot_orc_kpi > 0 else 0.0
        lucro_op = mrr_val - tot_real_kpi
        margem_pct = (lucro_op / mrr_val * 100) if mrr_val > 0 else 0.0

        if tot_orc_kpi > 0:
            var_custos = ((tot_real_kpi - tot_orc_kpi) / tot_orc_kpi) * 100
            delta_real_vs_orc = f"{var_custos:+.1f}% vs Orçamento"
        else:
            delta_real_vs_orc = None

        tot_orc_prev = b_prev["Orçado"].sum() if not b_prev.empty else 0.0
        delta_orc_pct = f"{((tot_orc_kpi - tot_orc_prev) / tot_orc_prev * 100):+.1f}% {rotulo_comparativo}" if tot_orc_prev > 0 else None
        delta_lucro = f"{margem_pct:.1f}% de Margem" if mrr_val > 0 else None

        st.markdown("##### 💼 Demonstrativo de Resultados (P&L)")
        k1, k2, k3 = st.columns(3)
        k1.metric("Receita Declarada", formatar_moeda(mrr_val))
        k2.metric("Custos Totais Realizados", formatar_moeda(tot_real_kpi), delta=delta_real_vs_orc, delta_color="inverse")
        k3.metric("Lucro Operacional Estimado", formatar_moeda(lucro_op), delta=delta_lucro, delta_color="normal")

        st.markdown("##### 🎯 Consumo de Budget Global")
        b1, b2, b3 = st.columns(3)
        b1.metric("Orçamento Total (Aba Budget)", formatar_moeda(tot_orc_kpi), delta=delta_orc_pct, delta_color="off")
        b2.metric("Saldo Disponível em Caixa", formatar_moeda(tot_orc_kpi - tot_real_kpi), "Estouro" if (tot_orc_kpi - tot_real_kpi) < 0 else "OK", delta_color="normal")
        with b3:
            st.markdown(f"**Burn Rate:** `{pct_consumo_budget:.1f}%`")
            st.progress(min(pct_consumo_budget / 100, 1.0))

        st.markdown("---")
        
        # Consolidação para Gráficos e Matriz
        b_grp = b_atual.groupby(["CONTA", "Nome da Conta"])["Orçado"].sum().reset_index() if not b_atual.empty else pd.DataFrame(columns=["CONTA", "Nome da Conta", "Orçado"])
        l_grp = l_atual.groupby("CONTA")["Realizado"].sum().reset_index() if not l_atual.empty else pd.DataFrame(columns=["CONTA", "Realizado"])
        
        df_bi = pd.merge(b_grp, l_grp, on="CONTA", how="outer").fillna(0)
        df_bi = df_bi[(df_bi["Orçado"] != 0) | (df_bi["Realizado"] != 0)]
        df_bi["Nome da Conta"] = np.where(df_bi["Nome da Conta"] == 0, df_bi["CONTA"], df_bi["Nome da Conta"])
        df_bi["Saldo"] = df_bi["Orçado"] - df_bi["Realizado"]
        
        linha1_col1, line1_col2 = st.columns([3, 2])
        with linha1_col1:
            df_chart1 = df_bi.set_index("Nome da Conta")[["Orçado", "Realizado"]].sort_values("Realizado", ascending=False).head(10).reset_index()
            fig_vs = px.bar(df_chart1, x="Nome da Conta", y=["Orçado", "Realizado"], barmode="group", title="Orçamento vs Execução (Top 10 Contas)", color_discrete_map={"Orçado": "#1f77b4", "Realizado": "#ff7f0e"})
            fig_vs.update_layout(xaxis_title="", yaxis_title="Valor (R$)", legend_title_text="", margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig_vs, use_container_width=True)
        with line1_col2:
            fig_waterfall = go.Figure(go.Waterfall(
                name="P&L", orientation="v", measure=["relative", "relative", "total"], x=["Receita", "Custos", "Resultado"], textposition="outside",
                text=[f"R$ {mrr_val:,.0f}", f"R$ {-tot_real_kpi:,.0f}", f"R$ {lucro_op:,.0f}"], y=[mrr_val, -tot_real_kpi, lucro_op],
                connector={"line": {"color": "rgb(63, 63, 63)"}}, decreasing={"marker": {"color": "#d62728"}}, increasing={"marker": {"color": "#2ca02c"}}, totals={"marker": {"color": "#1f77b4"}}
            ))
            fig_waterfall.update_layout(title="Formação do Resultado (Cash Burn)", margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig_waterfall, use_container_width=True)

        st.markdown("<br>", unsafe_allow_html=True)
        linha2_col1, linha2_col2 = st.columns(2)
        with linha2_col1:
            df_chart2 = df_bi.sort_values("Realizado", ascending=True).tail(7)
            fig_custos = px.bar(df_chart2, x="Realizado", y="Nome da Conta", orientation="h", title="Curva ABC: Maiores Ofensores", color_discrete_sequence=["#d62728"], text_auto='.2s')
            fig_custos.update_layout(xaxis_title="", yaxis_title="", margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig_custos, use_container_width=True)
        with linha2_col2:
            if not l_atual.empty and "Fornecedor" in l_atual.columns:
                df_forn = l_atual.groupby("Fornecedor")["Realizado"].sum().reset_index()
                df_chart3 = df_forn[df_forn["Realizado"] > 0].sort_values("Realizado", ascending=True).tail(7)
                fig_forn = px.bar(df_chart3, x="Realizado", y="Fornecedor", orientation="h", title="Concentração por Fornecedor (Top 7)", color_discrete_sequence=["#2ca02c"], text_auto='.2s')
                fig_forn.update_layout(xaxis_title="", yaxis_title="", margin=dict(t=40, b=0, l=0, r=0))
                st.plotly_chart(fig_forn, use_container_width=True)

        st.markdown("---")
        
        # =========================================================================
        # MATRIZ DE CUSTOS COM DRILL-DOWN INTERATIVO
        # =========================================================================
        st.markdown("##### 📋 Matriz de Custos")
        st.caption("🖱️ **Drill-down (Detalhamento):** Selecione uma linha na tabela abaixo para visualizar todos os lançamentos que compõem aquele custo.")
        
        df_bi["% Uso do Budget"] = np.where(df_bi["Orçado"] > 0, (df_bi["Realizado"] / df_bi["Orçado"]) * 100, np.where(df_bi["Realizado"] > 0, 100.0, 0))
        df_bi["% Consumo da Receita"] = np.where(mrr_val > 0, (df_bi["Realizado"] / mrr_val) * 100, 0)
        df_bi["Status"] = np.where(df_bi["Realizado"] > df_bi["Orçado"], "🔴 Estourou", np.where(df_bi["Realizado"] >= df_bi["Orçado"] * 0.85, "🟡 Alerta", "🟢 OK"))
        df_bi["Status"] = np.where((df_bi["Orçado"] == 0) & (df_bi["Realizado"] == 0), "⚪ Sem Movimento", df_bi["Status"])
        
        # Preparação do View (Index sequencial para o evento de clique)
        df_view = df_bi[["Status", "CONTA", "Nome da Conta", "Orçado", "Realizado", "Saldo", "% Uso do Budget", "% Consumo da Receita"]].sort_values("Realizado", ascending=False).reset_index(drop=True)
        
        # Captura de Evento Nativo do Streamlit (on_select)
        event = st.dataframe(
            df_view,
            selection_mode="single-row",
            on_select="rerun",
            key="grid_matriz",
            column_config={
                "CONTA": None, # Oculta a chave SAP (usada apenas para filtrar)
                "Status": st.column_config.TextColumn("Alerta"), 
                "Nome da Conta": st.column_config.TextColumn("Conta (Budget)"),
                "Orçado": st.column_config.NumberColumn("Budget", format="R$ %.2f"), 
                "Realizado": st.column_config.NumberColumn("Realizado", format="R$ %.2f"),
                "Saldo": st.column_config.NumberColumn("Saldo", format="R$ %.2f"),
                "% Uso do Budget": st.column_config.ProgressColumn("🔥 Consumo", format="%.1f%%", min_value=0, max_value=100),
                "% Consumo da Receita": st.column_config.ProgressColumn("Peso Receita", format="%.2f%%", min_value=0, max_value=100)
            }, hide_index=True, use_container_width=True
        )

        # Renderização Dinâmica do Detalhamento (Sub-tabela)
        if event and len(event.selection.rows) > 0:
            idx_selecionado = event.selection.rows[0]
            conta_alvo = df_view.iloc[idx_selecionado]["CONTA"]
            nome_conta = df_view.iloc[idx_selecionado]["Nome da Conta"]

            st.markdown(f"###### 🔎 Composição de Custos: `{nome_conta}`")
            
            # Filtra do DataFrame primário de lançamentos (Query 2025)
            df_drill = l_atual[l_atual["CONTA"] == conta_alvo].copy()
            
            if not df_drill.empty:
                cols_exibicao = [c for c in ["Competência", "Fornecedor", "Centro de Custo", "Realizado", "Observações"] if c in df_drill.columns]
                st.dataframe(
                    df_drill[cols_exibicao].sort_values("Realizado", ascending=False),
                    column_config={"Realizado": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f")},
                    hide_index=True, use_container_width=True
                )
            else:
                st.info("Nenhum lançamento físico associado a esta conta no período (Saldo provém exclusivamente do Planejamento/Budget).")

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
                        "Mês": data_mes.strftime("%Y-%m-%d"), "Cta.contáb./cód.PN": conta_sap_san,
                        "Débito/crédito (MC)": str(valor_deb_cred).replace(".", ","), "Observações": sanitizar_input(observacoes),
                        "Fornecedor": fornecedor_san, "Centro de Custo": sanitizar_input(centro_custo), "FORNECEDOR": fornecedor_san,
                        "Cta.contáb./cód.PN 2": conta_sap_san, "Conta Contabil": conta_sap_san
                    }
                    nova_linha = [dados_insert.get(col, "") for col in cabecalhos]
                    worksheet.append_row(nova_linha)
                    st.success("✅ Lançamento auditado e inserido com sucesso.")
                    extrair_dados_nuvem_v6.clear() 
                except Exception as e:
                    st.error(f"🚨 Falha na transação DML: {e}")
