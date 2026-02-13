import streamlit as st
import pandas as pd

st.set_page_config(page_title="Controle de Estoque", layout="wide")

st.title("Controle de Estoque - Reposição Visual")

# Estado inicial da tabela (fica só em memória, pra testar o layout)
if "df_estoque" not in st.session_state:
    st.session_state.df_estoque = pd.DataFrame(
        [
            {
                "produto": "Exemplo 1",
                "sku": "SKU001",
                "qtd_atual": 5,
                "ponto_reposicao": 10,
                "status_reposicao": "nao_solicitado",
                "disponivel_mercado": True,
            },
            {
                "produto": "Exemplo 2",
                "sku": "SKU002",
                "qtd_atual": 2,
                "ponto_reposicao": 5,
                "status_reposicao": "solicitado",
                "disponivel_mercado": True,
            },
        ]
    )

df = st.session_state.df_estoque

# KPIs simples
col1, col2, col3 = st.columns(3)
total_itens = len(df)
estoque_baixo = (df["qtd_atual"] <= df["ponto_reposicao"]).sum()
em_reposicao = (df["status_reposicao"].isin(["solicitado", "em_transito"])).sum()

col1.metric("Itens cadastrados", total_itens)
col2.metric("Estoque baixo/critico", estoque_baixo)
col3.metric("Em reposição", em_reposicao)

st.subheader("Tabela de produtos")

edited_df = st.data_editor(
    df,
    num_rows="dynamic",  # permite adicionar/remover linhas [web:104][web:106]
    hide_index=True,
)

st.session_state.df_estoque = edited_df

st.caption("Você pode editar as células e adicionar novas linhas. Os dados ficam salvos enquanto o app estiver aberto.")
