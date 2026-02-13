import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path("estoque.db")


# ---------- Funções de banco ----------

def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produto TEXT,
            sku TEXT,
            qtd_atual INTEGER,
            ponto_reposicao INTEGER,
            status_reposicao TEXT,
            disponivel_mercado INTEGER
        )
        """
    )
    conn.commit()
    conn.close()


def load_data() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM produtos", conn)
    conn.close()
    return df


def save_changes(df_editado: pd.DataFrame, df_original: pd.DataFrame):
    conn = get_conn()
    cur = conn.cursor()

    # Atualizar linhas existentes
    for _, row in df_editado.iterrows():
        if pd.notna(row["id"]):
            cur.execute(
                """
                UPDATE produtos SET
                    produto = ?,
                    sku = ?,
                    qtd_atual = ?,
                    ponto_reposicao = ?,
                    status_reposicao = ?,
                    disponivel_mercado = ?
                WHERE id = ?
                """,
                (
                    row.get("produto"),
                    row.get("sku"),
                    int(row["qtd_atual"]) if pd.notna(row["qtd_atual"]) else None,
                    int(row["ponto_reposicao"]) if pd.notna(row["ponto_reposicao"]) else None,
                    row.get("status_reposicao") or "nao_solicitado",
                    int(row["disponivel_mercado"]) if pd.notna(row["disponivel_mercado"]) else 1,
                    int(row["id"]),
                ),
            )

    # Inserir novas linhas (id vazio)
    novos = df_editado[df_editado["id"].isna()]
    for _, row in novos.iterrows():
        cur.execute(
            """
            INSERT INTO produtos
                (produto, sku, qtd_atual, ponto_reposicao, status_reposicao, disponivel_mercado)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("produto"),
                row.get("sku"),
                int(row["qtd_atual"]) if pd.notna(row["qtd_atual"]) else None,
                int(row["ponto_reposicao"]) if pd.notna(row["ponto_reposicao"]) else None,
                row.get("status_reposicao") or "nao_solicitado",
                int(row["disponivel_mercado"]) if pd.notna(row["disponivel_mercado"]) else 1,
            ),
        )

    conn.commit()
    conn.close()


# ---------- App Streamlit ----------

st.set_page_config(page_title="Controle de Estoque", layout="wide")
st.title("Controle de Estoque - Reposição Visual com SQLite")

init_db()

df = load_data()

# Se o banco estiver vazio, cria alguns exemplos
if df.empty:
    df = pd.DataFrame(
        [
            {
                "id": None,
                "produto": "Exemplo 1",
                "sku": "SKU001",
                "qtd_atual": 5,
                "ponto_reposicao": 10,
                "status_reposicao": "nao_solicitado",
                "disponivel_mercado": 1,
            },
            {
                "id": None,
                "produto": "Exemplo 2",
                "sku": "SKU002",
                "qtd_atual": 2,
                "ponto_reposicao": 5,
                "status_reposicao": "solicitado",
                "disponivel_mercado": 1,
            },
        ]
    )

# KPIs simples
total_itens = len(df)
estoque_baixo = (df["qtd_atual"] <= df["ponto_reposicao"]).sum()
em_reposicao = df["status_reposicao"].isin(["solicitado", "em_transito"]).sum()

col1, col2, col3 = st.columns(3)
col1.metric("Itens cadastrados", total_itens)
col2.metric("Estoque baixo/critico", int(estoque_baixo))
col3.metric("Em reposição", int(em_reposicao))

st.subheader("Tabela de produtos (dados salvos em SQLite)")

column_config = {
    "disponivel_mercado": st.column_config.CheckboxColumn("Disponível no mercado"),
    "status_reposicao": st.column_config.SelectboxColumn(
        "Status reposição",
        options=["nao_solicitado", "solicitado", "em_transito", "recebido"],
    ),
}

edited_df = st.data_editor(
    df,
    num_rows="dynamic",
    hide_index=True,
    column_config=column_config,
    use_container_width=True,
)

if st.button("Salvar alterações no banco"):
    save_changes(edited_df, df)
    st.success("Alterações salvas em estoque.db. Recarregue a página para ver os dados atualizados.")
