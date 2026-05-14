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

# --- FUNÇÃO DE SALVAMENTO (CALLBACK CONTRA DUPLICIDADE) ---
def salvar_venda_callback():
    # Recupera os valores do session_state
    p_id = st.session_state.sel_prod_id
    qtd = st.session_state.input_qtd
    prc = st.session_state.input_prc
    taxa = st.session_state.input_taxa if st.session_state.get('chk_taxa') else 0.0
    dt = st.session_state.input_dt
    
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO vendas (produto_id, quantidade, preco_unitario_venda, data_venda, taxa_entrega)
                        VALUES (:id, :q, :p, :d, :t)"""),
                {"id": p_id, "q": qtd, "p": prc, "d": dt, "t": taxa}
            )
        st.toast("✅ Venda registrada com sucesso!", icon="💰")
    except Exception as e:
        st.error(f"Erro ao salvar no banco: {e}")

# --- NAVEGAÇÃO ---
st.sidebar.title("Pudins da Thamy 🍮")
choice = st.sidebar.selectbox("Navegação", ["Dashboard Financeiro", "Registrar Venda", "Gerenciar Produtos"])

if engine is None:
    st.error("Banco de dados não conectado. Verifique o arquivo .env.")
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
        
        # KPIs
        c1, c2, c3 = st.columns(3)
        c1.metric("Faturamento Total", f"R$ {df['faturamento'].sum():,.2f}")
        c2.metric("Custo Total", f"R$ {df['custo_total'].sum():,.2f}")
        lucro_total = df['lucro'].sum()
        c3.metric("Lucro Líquido", f"R$ {lucro_total:,.2f}", delta_color="normal" if lucro_total >= 0 else "inverse")

        # --- GRÁFICO MENSALIZADO ---
        st.subheader("📈 Comparativo Mensal (Faturamento x Custo x Lucro)")
        df_m = df.copy()
        df_m['Mês'] = df_m['data_venda'].dt.strftime('%Y-%m')
        df_grouped = df_m.groupby('Mês')[['faturamento', 'custo_total', 'lucro']].sum().reset_index()
        
        # Formato Longo para o Plotly
        df_melt = df_grouped.melt(id_vars='Mês', var_name='Indicador', value_name='Valor')
        
        fig = px.bar(df_melt, x='Mês', y='Valor', color='Indicador', barmode='group',
                     color_discrete_map={'faturamento': '#2ecc71', 'custo_total': '#e74c3c', 'lucro': '#3498db'},
                     text_auto='.2s')
        st.plotly_chart(fig, use_container_width=True)

        # Tabela
        st.subheader("📄 Histórico Detalhado")
        df_vis = df.copy()
        df_vis['data_venda'] = df_vis['data_venda'].dt.strftime('%d/%m/%Y')
        st.dataframe(df_vis.style.format({'faturamento': 'R$ {:.2f}', 'lucro': 'R$ {:.2f}', 'custo_total': 'R$ {:.2f}'}), use_container_width=True)
    else:
        st.info("Nenhuma venda encontrada.")

# --- ABA 2: REGISTRAR VENDA (COM LOGICA ANTI-DUPLICIDADE) ---
elif choice == "Registrar Venda":
    st.title("💰 Registrar Venda")
    df_p = run_query("SELECT id, nome FROM produtos ORDER BY nome")
    
    if df_p.empty:
        st.warning("Cadastre produtos primeiro.")
    else:
        with st.container(border=True):
            # Usamos keys no session_state para que o callback possa ler os dados
            nome_sel = st.selectbox("Produto", options=df_p['nome'].tolist())
            st.session_state.sel_prod_id = int(df_p[df_p['nome'] == nome_sel]['id'].values[0])
            
            col1, col2 = st.columns(2)
            st.number_input("Quantidade", min_value=1, key="input_qtd")
            st.number_input("Preço de Venda Unitário (R$)", min_value=0.0, format="%.2f", key="input_prc")
            
            st.checkbox("Incluir Taxa de Entrega?", key="chk_taxa")
            if st.session_state.chk_taxa:
                st.number_input("Valor da Entrega (R$)", min_value=0.0, format="%.2f", key="input_taxa")
            
            st.date_input("Data da Venda", datetime.now(), key="input_dt")

            # O segredo está aqui: on_click chama a função UMA vez antes do app recarregar
            st.button("🚀 Finalizar Venda", on_click=salvar_venda_callback, type="primary", use_container_width=True)

# --- ABA 3: GERENCIAR PRODUTOS ---
elif choice == "Gerenciar Produtos":
    st.title("📦 Gestão de Produtos")
    tab1, tab2 = st.tabs(["Novo Produto", "Lista e Edição"])
    
    with tab1:
        with st.form("cad"):
            n = st.text_input("Nome")
            c = st.number_input("Custo Unitário", min_value=0.0)
            if st.form_submit_button("Salvar"):
                with engine.begin() as conn:
                    conn.execute(text("INSERT INTO produtos (nome, custo_unitario) VALUES (:n, :c)"), {"n":n, "c":c})
                st.success("Cadastrado!")
                st.rerun()
                
    with tab2:
        df_lista = run_query("SELECT * FROM produtos ORDER BY nome")
        st.dataframe(df_lista, use_container_width=True)
        if not df_lista.empty:
            st.divider()
            p_edit = st.selectbox("Editar Produto", df_lista['nome'])
            row = df_lista[df_lista['nome'] == p_edit].iloc[0]
            new_n = st.text_input("Novo Nome", value=row['nome'])
            new_c = st.number_input("Novo Custo", value=float(row['custo_unitario']))
            if st.button("Atualizar"):
                with engine.begin() as conn:
                    conn.execute(text("UPDATE produtos SET nome=:n, custo_unitario=:c WHERE id=:id"),
                                 {"n":new_n, "c":new_c, "id": int(row['id'])})
                st.success("Atualizado!")
                st.rerun()