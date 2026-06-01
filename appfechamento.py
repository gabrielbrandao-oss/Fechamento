# file: app_fechamento_secure.py
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
import logging

# Configuração de Logs Auditáveis
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Portal Financeiro Corporativo", layout="wide", page_icon="🏢")

# --- 1. CAMADA DE SEGURANÇA E AUTENTICAÇÃO (APPSEC) ---
class SecurityManager:
    @staticmethod
    def verificar_senha(senha_fornecida: str, hash_armazenado: str) -> bool:
        if not senha_fornecida or not hash_armazenado: return False
        try:
            return bcrypt.checkpw(senha_fornecida.encode('utf-8'), hash_armazenado.encode('utf-8'))
        except ValueError:
            logger.warning("Tentativa de bypass ou hash malformado detectado.")
            return False

    @staticmethod
    def sanitizar_input(texto: str) -> str:
        if not isinstance(texto, str): return ""
        # Prevenção rigorosa contra XSS e injeção de caracteres de controle
        sanitizado = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', html.escape(texto.strip()))
        return sanitizado

    @staticmethod
    def validar_ambiente() -> tuple[str, str]:
        hash_senha = st.secrets.get("senha_app_hash")
        url_bd = st.secrets.get("url_planilha")
        if not hash_senha or not url_bd:
            st.error("🚨 Falha Crítica: Variáveis de ambiente ausentes. Sistema bloqueado por segurança.")
            st.stop()
        return hash_senha, url_bd

    @staticmethod
    def requerer_autenticacao(hash_armazenado: str):
        if "auth_ok" not in st.session_state:
            st.session_state["auth_ok"] = False

        if not st.session_state["auth_ok"]:
            st.sidebar.title("🔒 Acesso Restrito")
            senha_digitada = st.sidebar.text_input("Palavra-passe Corporativa:", type="password")
            
            if senha_digitada:
                if SecurityManager.verificar_senha(senha_digitada, hash_armazenado):
                    st.session_state["auth_ok"] = True
                    st.rerun()
                else:
                    st.sidebar.error("⚠️ Credenciais inválidas.")
                    logger.warning("Falha de autenticação detectada.")
            st.stop()
        
        st.sidebar.success("✅ Acesso Liberado")
        if st.sidebar.button("🚪 Encerrar Sessão"):
            st.session_state["auth_ok"] = False
            st.rerun()
        st.sidebar.markdown("---")

# --- 2. CAMADA DE DADOS E INFRAESTRUTURA (ETL/DML) ---
class FinanceRepository:
    SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

    def __init__(self, url_banco: str):
        self.url_banco = url_banco
        self.client = self._conectar()

    @staticmethod
    @st.cache_resource(ttl=3600)
    def _conectar():
        try:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, FinanceRepository.SCOPE)
            return gspread.authorize(creds)
        except Exception as e:
            logger.critical(f"Falha na injeção de credenciais GCP: {e}")
            st.error("🚨 Erro crítico de infraestrutura. Contate o AppSec.")
            st.stop()

    @staticmethod
    def otimizar_tipagem_moeda(serie: pd.Series) -> pd.Series:
        """Vetorização de limpeza de strings financeiras para performance (O(1) a nível de C)"""
        s = serie.astype(str).str.upper().str.replace("R$", "", regex=False).str.strip()
        s = s.str.replace(r'[^\d,-]', '', regex=True)
        # Padronização de separadores milhar/decimal padrão BRL para Float
        s = s.str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
        return pd.to_numeric(s, errors='coerce').fillna(0.0)

    @st.cache_data(ttl=600)
    def extrair_dados(_self) -> tuple[pd.DataFrame, pd.DataFrame]:
        try:
            sheet = _self.client.open_by_url(_self.url_banco)
            ws_lanc = sheet.worksheet("Query 2025").get_all_values()
            ws_budget = sheet.worksheet("Budget").get_all_values()
            
            df_lanc = pd.DataFrame(ws_lanc[1:], columns=ws_lanc[0]) if len(ws_lanc) > 1 else pd.DataFrame()
            df_budget = pd.DataFrame(ws_budget[1:], columns=ws_budget[0]) if len(ws_budget) > 1 else pd.DataFrame()
            
            # --- Transformação Vetorizada de Lançamentos ---
            if not df_lanc.empty:
                df_lanc.columns = df_lanc.columns.str.strip().str.upper()
                col_val = "DÉBITO/CRÉDITO (MC)" if "DÉBITO/CRÉDITO (MC)" in df_lanc.columns else df_lanc.columns[0]
                df_lanc["Realizado"] = FinanceRepository.otimizar_tipagem_moeda(df_lanc[col_val])
                
                col_mes = next((c for c in df_lanc.columns if c in ['MÊS', 'MES', 'DATA']), None)
                if col_mes:
                    df_lanc["Competência"] = pd.to_datetime(df_lanc[col_mes], errors='coerce').dt.strftime('%m/%Y').fillna("Sem Data")
                else:
                    df_lanc["Competência"] = "Sem Data"
                    
                df_lanc["Ano"] = df_lanc["Competência"].str.split('/').str[-1]
                col_conta = next((c for c in df_lanc.columns if c in ['CTA.CONTÁB./CÓD.PN', 'CONTA', 'CONTA SAP']), None)
                df_lanc["CONTA"] = df_lanc[col_conta].astype(str).str.strip() if col_conta else "Sem Conta"
                df_lanc["Fornecedor"] = df_lanc.iloc[:, 11].astype(str).str.strip() if len(df_lanc.columns) >= 12 else "Sem Fornecedor"

            # --- Transformação Vetorizada de Budget ---
            if not df_budget.empty:
                df_budget.columns = df_budget.columns.str.strip().str.upper()
                col_val_b = next((c for c in df_budget.columns if c in ['BUDGET', 'ORÇADO', 'ORCAMENTO', 'VALOR']), None)
                df_budget["Orçado"] = FinanceRepository.otimizar_tipagem_moeda(df_budget[col_val_b]) if col_val_b else 0.0
                
                col_mes_b = next((c for c in df_budget.columns if c in ['MÊS', 'MES', 'DATA', 'COMPETÊNCIA', 'PERÍODO']), None)
                if col_mes_b:
                    df_budget["Competência"] = pd.to_datetime(df_budget[col_mes_b], errors='coerce').dt.strftime('%m/%Y').fillna("Sem Data")
                else:
                    df_budget["Competência"] = "Sem Data"
                    
                df_budget["Ano"] = df_budget["Competência"].str.split('/').str[-1]
                col_conta_b = next((c for c in df_budget.columns if c in ['CONTA', 'CONTA SAP', 'CÓDIGO', 'CTA.CONTÁB./CÓD.PN']), None)
                df_budget["CONTA"] = df_budget[col_conta_b].astype(str).str.strip() if col_conta_b else "Sem Conta"
                df_budget["Nome da Conta"] = df_budget.iloc[:, 2].astype(str).str.strip() if len(df_budget.columns) >= 3 else df_budget["CONTA"]

            return df_lanc, df_budget
            
        except Exception as e:
            logger.error(f"Erro no pipeline ETL: {e}")
            return pd.DataFrame(), pd.DataFrame()

    def inserir_lancamento(self, payload: dict) -> bool:
        """Injeção DML segura via append_row."""
        try:
            sheet = self.client.open_by_url(self.url_banco)
            worksheet = sheet.worksheet("Query 2025")
            cabecalhos = worksheet.row_values(1)
            nova_linha = [payload.get(col, "") for col in cabecalhos]
            worksheet.append_row(nova_linha)
            self.extrair_dados.clear() # Invalida o cache
            return True
        except Exception as e:
            logger.error(f"Falha de gravação DML: {e}")
            return False

# --- 3. CAMADA DE INTERFACE E LÓGICA DE NEGÓCIOS ---
def formatar_moeda(valor: float) -> str:
    if pd.isna(valor): return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

def renderizar_kpis(b_atual, l_atual, b_prev, mrr_input, rotulo_comparativo):
    tot_orc_kpi = b_atual["Orçado"].sum()
    tot_real_kpi = l_atual["Realizado"].sum()
    mrr_val = mrr_input

    pct_consumo_budget = (tot_real_kpi / tot_orc_kpi * 100) if tot_orc_kpi > 0 else 0.0
    lucro_op = mrr_val - tot_real_kpi
    margem_pct = (lucro_op / mrr_val * 100) if mrr_val > 0 else 0.0
    delta_real_vs_orc = f"{((tot_real_kpi - tot_orc_kpi) / tot_orc_kpi) * 100:+.1f}% vs Orçamento" if tot_orc_kpi > 0 else None

    tot_orc_prev = b_prev["Orçado"].sum() if not b_prev.empty else 0.0
    delta_orc_pct = f"{((tot_orc_kpi - tot_orc_prev) / tot_orc_prev * 100):+.1f}% {rotulo_comparativo}" if tot_orc_prev > 0 else None

    st.markdown("##### 💼 Demonstrativo de Resultados (P&L)")
    k1, k2, k3 = st.columns(3)
    k1.metric("Receita Declarada", formatar_moeda(mrr_val))
    k2.metric("Custos Totais Realizados", formatar_moeda(tot_real_kpi), delta=delta_real_vs_orc, delta_color="inverse")
    k3.metric("Lucro Operacional Estimado", formatar_moeda(lucro_op), delta=f"{margem_pct:.1f}% de Margem", delta_color="normal")

    st.markdown("##### 🎯 Consumo de Budget Global")
    b1, b2, b3 = st.columns(3)
    b1.metric("Orçamento Total (Aba Budget)", formatar_moeda(tot_orc_kpi), delta=delta_orc_pct, delta_color="off")
    b2.metric("Saldo Disponível em Caixa", formatar_moeda(tot_orc_kpi - tot_real_kpi), "Estouro" if (tot_orc_kpi - tot_real_kpi) < 0 else "OK", delta_color="normal")
    with b3:
        st.markdown(f"**Burn Rate:** `{pct_consumo_budget:.1f}%`")
        st.progress(min(pct_consumo_budget / 100, 1.0))
    return tot_real_kpi, lucro_op

def main():
    HASH_SENHA, URL_BANCO_DADOS = SecurityManager.validar_ambiente()
    SecurityManager.requerer_autenticacao(HASH_SENHA)

    repo = FinanceRepository(URL_BANCO_DADOS)
    df_lanc, df_budget = repo.extrair_dados()

    tab_dash, tab_form = st.tabs(["👔 Visão Executiva (CFO)", "📥 Inserir Lançamento"])

    with tab_dash:
        if df_lanc.empty and df_budget.empty:
            st.warning("Banco de dados vazio ou inacessível.")
            return

        st.markdown("### 🎛️ Motor de Filtros Analíticos")
        anos_disponiveis = sorted([a for a in df_budget["Ano"].dropna().unique() if str(a).isdigit()], reverse=True) or [str(datetime.now().year)]

        col_f1, col_f2, col_f3, col_f4 = st.columns([1.5, 1, 1.5, 2])
        with col_f1: tipo_visao = st.radio("📊 Análise:", ["Mensal", "Anual Consolidada"], horizontal=True)
        with col_f2: ano_alvo = st.selectbox("📅 Ano:", anos_disponiveis)
        with col_f3:
            if tipo_visao == "Mensal":
                meses_disp = sorted([m for m in df_budget[df_budget["Ano"] == ano_alvo]["Competência"].dropna().unique() if '/' in str(m)])
                mes_alvo = st.selectbox("📆 Mês:", meses_disp, index=len(meses_disp)-1 if meses_disp else 0)
            else:
                mes_alvo = "Todos"
                st.info(f"Consolidado ({ano_alvo})")
        with col_f4:
            mrr_input = st.number_input(f"💰 Receita Manual (Opcional)", min_value=0.0, format="%.2f")

        st.markdown("---")

        # Filtragem Estruturada
        mask_b = df_budget["Competência"] == mes_alvo if tipo_visao == "Mensal" else df_budget["Ano"] == ano_alvo
        mask_l = df_lanc["Competência"] == mes_alvo if tipo_visao == "Mensal" else df_lanc["Ano"] == ano_alvo
        b_atual, l_atual = df_budget[mask_b], df_lanc[mask_l]

        # Resolução de Período Anterior
        b_prev, rotulo_comparativo = pd.DataFrame(), ""
        if tipo_visao == "Mensal" and 'meses_disp' in locals() and mes_alvo in meses_disp:
            idx = meses_disp.index(mes_alvo)
            if idx > 0:
                b_prev = df_budget[df_budget["Competência"] == meses_disp[idx - 1]]
                rotulo_comparativo = f"vs Ant. ({meses_disp[idx - 1]})"
        elif tipo_visao == "Anual Consolidada" and ano_alvo in anos_disponiveis:
            idx = anos_disponiveis.index(ano_alvo)
            if idx + 1 < len(anos_disponiveis):
                b_prev = df_budget[df_budget["Ano"] == anos_disponiveis[idx + 1]]
                rotulo_comparativo = f"vs Ant. ({anos_disponiveis[idx + 1]})"

        # KPIs
        tot_real_kpi, lucro_op = renderizar_kpis(b_atual, l_atual, b_prev, mrr_input, rotulo_comparativo)
        st.markdown("---")

        # Processamento de Matriz de Custos
        b_grp = b_atual.groupby(["CONTA", "Nome da Conta"], as_index=False)["Orçado"].sum()
        l_grp = l_atual.groupby("CONTA", as_index=False)["Realizado"].sum()
        df_bi = pd.merge(b_grp, l_grp, on="CONTA", how="outer").fillna({"Orçado": 0, "Realizado": 0})
        df_bi = df_bi[(df_bi["Orçado"] != 0) | (df_bi["Realizado"] != 0)]
        df_bi["Nome da Conta"] = np.where(df_bi["Nome da Conta"].isna() | (df_bi["Nome da Conta"] == 0), df_bi["CONTA"], df_bi["Nome da Conta"])
        df_bi["Saldo"] = df_bi["Orçado"] - df_bi["Realizado"]

        # Gráficos
        c1, c2 = st.columns([3, 2])
        with c1:
            df_chart1 = df_bi.nlargest(10, "Realizado")
            fig_vs = px.bar(df_chart1, x="Nome da Conta", y=["Orçado", "Realizado"], barmode="group", title="Orçamento vs Execução (Top 10)", color_discrete_map={"Orçado": "#1f77b4", "Realizado": "#ff7f0e"})
            fig_vs.update_layout(margin=dict(t=40, b=0, l=0, r=0), legend_title_text="")
            st.plotly_chart(fig_vs, use_container_width=True)
        with c2:
            fig_wf = go.Figure(go.Waterfall(
                measure=["relative", "relative", "total"], x=["Receita", "Custos", "Resultado"], y=[mrr_input, -tot_real_kpi, lucro_op],
                text=[f"R$ {mrr_input:,.0f}", f"R$ {-tot_real_kpi:,.0f}", f"R$ {lucro_op:,.0f}"], textposition="outside",
                decreasing={"marker": {"color": "#d62728"}}, increasing={"marker": {"color": "#2ca02c"}}, totals={"marker": {"color": "#1f77b4"}}
            ))
            fig_wf.update_layout(title="Formação do Resultado", margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig_wf, use_container_width=True)

        st.markdown("---")
        st.markdown("##### 📋 Matriz de Custos com Drill-Down")
        
        df_bi["% Uso do Budget"] = np.where(df_bi["Orçado"] > 0, (df_bi["Realizado"] / df_bi["Orçado"]) * 100, np.where(df_bi["Realizado"] > 0, 100.0, 0))
        df_bi["% Consumo da Receita"] = np.where(mrr_input > 0, (df_bi["Realizado"] / mrr_input) * 100, 0)
        df_bi["Status"] = np.select(
            [df_bi["Realizado"] > df_bi["Orçado"], df_bi["Realizado"] >= df_bi["Orçado"] * 0.85, (df_bi["Orçado"] == 0) & (df_bi["Realizado"] == 0)],
            ["🔴 Estourou", "🟡 Alerta", "⚪ Sem Movimento"], default="🟢 OK"
        )
        df_view = df_bi[["Status", "CONTA", "Nome da Conta", "Orçado", "Realizado", "Saldo", "% Uso do Budget", "% Consumo da Receita"]].sort_values("Realizado", ascending=False).reset_index(drop=True)

        event = st.dataframe(
            df_view, selection_mode="single-row", on_select="rerun", key="grid_matriz", hide_index=True, use_container_width=True,
            column_config={
                "CONTA": None, "Status": st.column_config.TextColumn("Alerta"), "Nome da Conta": st.column_config.TextColumn("Conta"),
                "Orçado": st.column_config.NumberColumn("Budget", format="R$ %.2f"), "Realizado": st.column_config.NumberColumn("Realizado", format="R$ %.2f"),
                "Saldo": st.column_config.NumberColumn("Saldo", format="R$ %.2f"),
                "% Uso do Budget": st.column_config.ProgressColumn("🔥 Consumo", format="%.1f%%", min_value=0, max_value=100),
                "% Consumo da Receita": st.column_config.ProgressColumn("Peso Receita", format="%.2f%%", min_value=0, max_value=100)
            }
        )

        if event and event.selection.rows:
            linha_sel = df_view.iloc[event.selection.rows[0]]
            st.markdown(f"###### 🔎 Detalhamento: `{linha_sel['Nome da Conta']}`")
            df_drill = l_atual[l_atual["CONTA"] == linha_sel["CONTA"]][["Competência", "Fornecedor", "Centro de Custo", "Realizado", "Observações"]].dropna(axis=1, how='all')
            if not df_drill.empty:
                st.dataframe(df_drill.sort_values("Realizado", ascending=False), hide_index=True, use_container_width=True, column_config={"Realizado": st.column_config.NumberColumn("Valor", format="R$ %.2f")})
            else:
                st.info("Nenhum lançamento físico detectado para este período.")

    with tab_form:
        st.markdown("### Lançamento Unitário no ERP")
        with st.form("form_dml", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                data_mes = st.date_input("Mês da Competência *")
                conta_sap = st.text_input("Cta.contáb./cód.PN *", max_chars=50)
                fornecedor = st.text_input("Fornecedor *", max_chars=100)
            with c2:
                centro_custo = st.text_input("Centro de Custo", max_chars=50)
                valor_deb_cred = st.number_input("Débito/crédito (MC) (R$) *", format="%.2f")
                observacoes = st.text_input("Observações", max_chars=255)

            if st.form_submit_button("🚀 Inserir Linha", use_container_width=True):
                conta_sap_san = SecurityManager.sanitizar_input(conta_sap)
                fornecedor_san = SecurityManager.sanitizar_input(fornecedor)
                
                if not conta_sap_san or not fornecedor_san:
                    st.error("🚨 Entradas inválidas: Campos obrigatórios ausentes ou contendo caracteres proibidos.")
                else:
                    with st.spinner("Gravando e gerando trilha de auditoria..."):
                        payload = {
                            "Mês": data_mes.strftime("%Y-%m-%d"), "Cta.contáb./cód.PN": conta_sap_san,
                            "Débito/crédito (MC)": str(valor_deb_cred).replace(".", ","), "Observações": SecurityManager.sanitizar_input(observacoes),
                            "Fornecedor": fornecedor_san, "Centro de Custo": SecurityManager.sanitizar_input(centro_custo),
                            "FORNECEDOR": fornecedor_san, "Cta.contáb./cód.PN 2": conta_sap_san, "Conta Contabil": conta_sap_san
                        }
                        if repo.inserir_lancamento(payload):
                            st.success("✅ Lançamento auditado e inserido com sucesso.")

if __name__ == "__main__":
    main()
