import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
import urllib.parse
import plotly.express as px
import os
from dotenv import load_dotenv

# --- CONFIGURAÇÃO E AMBIENTE ---
load_dotenv()
st.set_page_config(page_title="Pudins da Thamy 🍮", layout="wide")

DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

@st.cache_resource
def get_connection():
    try:
        pw = urllib.parse.quote_plus(DB_PASS)
        conn_str = f"postgresql://{DB_USER}:{pw}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        return create_engine(conn_str)
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
        return None

engine = get_connection()

def run_query(query, params=None):
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn, params=params)

# --- INICIALIZAÇÃO DO BANCO ---
def init_db():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS produtos (
                id SERIAL PRIMARY KEY, nome VARCHAR(100) NOT NULL, custo_unitario FLOAT DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS vendas (
                id SERIAL PRIMARY KEY, produto_id INTEGER REFERENCES produtos(id),
                quantidade INTEGER NOT NULL, preco_unitario_venda FLOAT NOT NULL,
                data_venda DATE NOT NULL, taxa_entrega FLOAT DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS insumos (
                id SERIAL PRIMARY KEY, nome VARCHAR(100) NOT NULL, unidade_medida VARCHAR(20) NOT NULL
            );
            CREATE TABLE IF NOT EXISTS compras_insumos (
                id SERIAL PRIMARY KEY, insumo_id INTEGER REFERENCES insumos(id),
                quantidade FLOAT NOT NULL, preco_total FLOAT NOT NULL,
                data_compra DATE NOT NULL, fornecedor VARCHAR(100)
            );
        """))

if engine:
    init_db()

# --- CALLBACKS ---
def salvar_venda_callback():
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO vendas (produto_id, quantidade, preco_unitario_venda, data_venda, taxa_entrega)
                        VALUES (:id, :q, :p, :d, :t)"""),
                {
                    "id": st.session_state.sel_prod_id, 
                    "q": st.session_state.input_qtd, 
                    "p": st.session_state.input_prc, 
                    "d": st.session_state.input_dt, 
                    "t": st.session_state.input_taxa if st.session_state.get('chk_taxa') else 0.0
                }
            )
        st.toast("✅ Venda registrada!", icon="💰")
    except Exception as e:
        st.error(f"Erro: {e}")

def salvar_compra_callback():
    # Cálculo do total antes de salvar
    qtd = st.session_state.compra_qtd
    prc_unit = st.session_state.compra_unitario
    total_calculado = qtd * prc_unit
    
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO compras_insumos (insumo_id, quantidade, preco_total, data_compra, fornecedor)
                        VALUES (:id, :q, :p, :d, :f)"""),
                {
                    "id": st.session_state.compra_insumo_id,
                    "q": qtd,
                    "p": total_calculado,
                    "d": st.session_state.compra_dt,
                    "f": st.session_state.compra_forn
                }
            )
        st.toast(f"✅ Compra de R$ {total_calculado:.2f} registrada!", icon="🛒")
    except Exception as e:
        st.error(f"Erro: {e}")

# --- NAVEGAÇÃO ---
st.sidebar.title("Pudins da Thamy 🍮")
choice = st.sidebar.selectbox("Navegação", [
    "Dashboard Financeiro", 
    "Registrar Venda", 
    "Gestão de Estoque (Insumos)",
    "Gerenciar Produtos"
])

if engine is None:
    st.stop()

# --- ABA 1: DASHBOARD FINANCEIRO ---
if choice == "Dashboard Financeiro":
    st.title("📊 Performance Financeira")
    query = """
        SELECT v.data_venda, v.quantidade, v.preco_unitario_venda, v.taxa_entrega,
               p.nome AS produto, p.custo_unitario,
               ((v.quantidade * v.preco_unitario_venda) + v.taxa_entrega) AS faturamento,
               (v.quantidade * p.custo_unitario) AS custo_total
        FROM vendas v JOIN produtos p ON v.produto_id = p.id
        ORDER BY v.data_venda DESC
    """
    df = run_query(query)
    if not df.empty:
        df['lucro'] = df['faturamento'] - df['custo_total']
        df['data_venda'] = pd.to_datetime(df['data_venda'])
        c1, c2, c3 = st.columns(3)
        c1.metric("Faturamento Total", f"R$ {df['faturamento'].sum():,.2f}")
        c2.metric("Custo Total (Produtos)", f"R$ {df['custo_total'].sum():,.2f}")
        c3.metric("Lucro Estimado", f"R$ {df['lucro'].sum():,.2f}")
        
        df_m = df.copy()
        df_m['Mês'] = df_m['data_venda'].dt.strftime('%Y-%m')
        df_grouped = df_m.groupby('Mês')[['faturamento', 'custo_total', 'lucro']].sum().reset_index()
        fig = px.bar(df_grouped.melt(id_vars='Mês'), x='Mês', y='value', color='variable', barmode='group')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Nenhuma venda encontrada.")

# --- ABA 2: REGISTRAR VENDA ---
elif choice == "Registrar Venda":
    st.title("💰 Registrar Venda")
    df_p = run_query("SELECT id, nome FROM produtos ORDER BY nome")
    if df_p.empty:
        st.warning("Cadastre produtos primeiro.")
    else:
        with st.container(border=True):
            nome_sel = st.selectbox("Produto", options=df_p['nome'].tolist())
            st.session_state.sel_prod_id = int(df_p[df_p['nome'] == nome_sel]['id'].values[0])
            col1, col2 = st.columns(2)
            col1.number_input("Quantidade", min_value=1, key="input_qtd")
            col2.number_input("Preço de Venda Unitário (R$)", min_value=0.0, format="%.2f", key="input_prc")
            st.checkbox("Incluir Taxa de Entrega?", key="chk_taxa")
            if st.session_state.chk_taxa:
                st.number_input("Valor da Entrega (R$)", min_value=0.0, key="input_taxa")
            st.date_input("Data da Venda", datetime.now(), key="input_dt")
            st.button("🚀 Finalizar Venda", on_click=salvar_venda_callback, type="primary", use_container_width=True)

# --- ABA 3: GESTÃO DE ESTOQUE (INSUMOS) ---
elif choice == "Gestão de Estoque (Insumos)":
    st.title("🛒 Gestão de Insumos")
    t1, t2, t3 = st.tabs(["Registrar Compra", "Análise de Gastos", "Cadastrar Novo Insumo"])

    with t3:
        st.subheader("Cadastro de Matéria-Prima")
        with st.form("cad_insumo"):
            n_i = st.text_input("Nome do Insumo (Ex: Leite Condensado)")
            u_i = st.selectbox("Unidade de Medida", ["Unidade", "Kg", "Grama", "Litro", "ML", "Caixa"])
            if st.form_submit_button("Cadastrar"):
                with engine.begin() as conn:
                    conn.execute(text("INSERT INTO insumos (nome, unidade_medida) VALUES (:n, :u)"), {"n": n_i, "u": u_i})
                st.success("Insumo cadastrado!")
                st.rerun()

    with t1:
        st.subheader("Lançar Compra de Mercadoria")
        df_i = run_query("SELECT * FROM insumos ORDER BY nome")
        if df_i.empty:
            st.info("Cadastre um insumo primeiro.")
        else:
            with st.container(border=True):
                ins_nome = st.selectbox("Selecione o Insumo", df_i['nome'].tolist())
                st.session_state.compra_insumo_id = int(df_i[df_i['nome'] == ins_nome]['id'].values[0])
                
                col1, col2, col3 = st.columns(3)
                # Input de Quantidade
                qtd_c = col1.number_input("Qtd Comprada", min_value=0.01, step=0.01, key="compra_qtd")
                # NOVO: Input de Valor Unitário
                unit_c = col2.number_input("Preço Unitário (R$)", min_value=0.01, step=0.01, key="compra_unitario")
                # Data
                dt_c = col3.date_input("Data da Compra", datetime.now(), key="compra_dt")
                
                # Cálculo automático para exibição
                total_preview = qtd_c * unit_c
                
                st.write(f"### 💵 Total a Pagar: **R$ {total_preview:,.2f}**")
                
                st.text_input("Fornecedor / Local", key="compra_forn")
                
                st.button("💾 Salvar Compra", on_click=salvar_compra_callback, use_container_width=True, type="primary")

    with t2:
        st.subheader("📊 Relatório de Compras")
        query_relatorio = """
            SELECT c.data_compra, i.nome as insumo, c.quantidade, i.unidade_medida, 
                   c.preco_total, (c.preco_total / c.quantidade) as preco_unit_pago, c.fornecedor
            FROM compras_insumos c JOIN insumos i ON c.insumo_id = i.id
            ORDER BY c.data_compra DESC
        """
        df_c = run_query(query_relatorio)
        if not df_c.empty:
            df_c['data_compra'] = pd.to_datetime(df_c['data_compra'])
            st.plotly_chart(px.line(df_c.groupby('data_compra')['preco_total'].sum().reset_index(), x='data_compra', y='preco_total'), use_container_width=True)
            st.dataframe(df_c, use_container_width=True)
        else:
            st.info("Sem compras.")

# --- ABA 4: GERENCIAR PRODUTOS ---
elif choice == "Gerenciar Produtos":
    st.title("📦 Gestão de Produtos")
    tab1, tab2 = st.tabs(["Novo Produto", "Lista e Edição"])
    with tab1:
        with st.form("cad_p"):
            n = st.text_input("Nome do Produto")
            c = st.number_input("Custo de Produção (R$)", min_value=0.0)
            if st.form_submit_button("Salvar"):
                with engine.begin() as conn:
                    conn.execute(text("INSERT INTO produtos (nome, custo_unitario) VALUES (:n, :c)"), {"n":n, "c":c})
                st.rerun()
    with tab2:
        df_l = run_query("SELECT * FROM produtos ORDER BY nome")
        st.dataframe(df_l, use_container_width=True)