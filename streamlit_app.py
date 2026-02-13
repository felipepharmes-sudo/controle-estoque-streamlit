import sqlite3
from pathlib import Path
from datetime import date

import pandas as pd
import streamlit as st
import altair as alt  # gráfico


# Caminho do banco SQLite
DB_PATH = Path("estoque.db")


# ---------- Funções de banco ----------

def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    """Garante que a tabela exista e, se estiver com colunas antigas, recria o banco."""
    required_cols = [
        "id",
        "produto",
        "sku",
        "qtd_atual",
        "ponto_reposicao",
        "status_reposicao",
        "disponivel_mercado",
        "fornecedor",
        "data_ultima_compra",
        "previsao_entrega",
    ]

    # Se o arquivo já existir, checa se falta alguma coluna
    if DB_PATH.exists():
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(produtos)")
            rows = cur.fetchall()
            conn.close()

            existing_cols = [r[1] for r in rows]  # nome da coluna é índice 1

            # Se a tabela existir e estiver incompleta, apaga o banco pra recriar limpo
            if existing_cols and any(col not in existing_cols for col in required_cols):
                DB_PATH.unlink()  # deleta estoque.db antigo
        except Exception:
            # Se der qualquer erro bizarro, também recria o banco
            if DB_PATH.exists():
                DB_PATH.unlink()

    # Cria a tabela com o esquema completo
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
            disponivel_mercado INTEGER,
            fornecedor TEXT,
            data_ultima_compra TEXT,
            previsao_entrega TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def load_data() -> pd.DataFrame:
    """Lê todos os produtos do banco para um DataFrame."""
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM produtos", conn)
    conn.close()
    return df


def save_changes(df_editado: pd.DataFrame):
    """Aplica INSERT/UPDATE no SQLite com base no DataFrame editado."""
    conn = get_conn()
    cur = conn.cursor()

    # Linhas que já têm id -> UPDATE
    existentes = df_editado[df_editado["id"].notna()]
    for _, row in existentes.iterrows():
        cur.execute(
            """
            UPDATE produtos SET
                produto = ?,
                sku = ?,
                qtd_atual = ?,
                ponto_reposicao = ?,
                status_reposicao = ?,
                disponivel_mercado = ?,
                fornecedor = ?,
                data_ultima_compra = ?,
                previsao_entrega = ?
            WHERE id = ?
            """,
            (
                row.get("produto"),
                row.get("sku"),
                int(row["qtd_atual"]) if pd.notna(row["qtd_atual"]) else None,
                int(row["ponto_reposicao"]) if pd.notna(row["ponto_reposicao"]) else None,
                row.get("status_reposicao") or "nao_solicitado",
                int(row["disponivel_mercado"]) if pd.notna(row["disponivel_mercado"]) else 1,
                row.get("fornecedor"),
                row.get("data_ultima_compra"),
                row.get("previsao_entrega"),
                int(row["id"]),
            ),
        )

    # Linhas novas (sem id) -> INSERT
    novos = df_editado[df_editado["id"].isna()]
    for _, row in novos.iterrows():
        cur.execute(
            """
            INSERT INTO produtos
                (produto, sku, qtd_atual, ponto_reposicao, status_reposicao,
                 disponivel_mercado, fornecedor, data_ultima_compra, previsao_entrega)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("produto"),
                row.get("sku"),
                int(row["qtd_atual"]) if pd.notna(row["qtd_atual"]) else None,
                int(row["ponto_reposicao"]) if pd.notna(row["ponto_reposicao"]) else None,
                row.get("status_reposicao") or "nao_solicitado",
                int(row["disponivel_mercado"]) if pd.notna(row["disponivel_mercado"]) else 1,
                row.get("fornecedor"),
                row.get("data_ultima_compra"),
                row.get("previsao_entrega"),
            ),
        )

    conn.commit()
    conn.close()


# ---------- App Streamlit ----------

st.set_page_config(page_title="Controle de Estoque", layout="wide")
st.title("Controle de Estoque - Reposição Visual com SQLite")

init_db()
df = load_data()

# Se o banco estiver vazio, cria alguns exemplos iniciais em memória
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
                "fornecedor": "Fornecedor A",
                "data_ultima_compra": None,
                "previsao_entrega": None,
            },
            {
                "id": None,
                "produto": "Exemplo 2",
                "sku": "SKU002",
                "qtd_atual": 0,
                "ponto_reposicao": 5,
                "status_reposicao": "solicitado",
                "disponivel_mercado": 0,
                "fornecedor": "Fornecedor B",
                "data_ultima_compra": None,
                "previsao_entrega": None,
            },
        ]
    )

# Garante que todas as colunas esperadas existam (se o banco for antigo)
for col in [
    "produto",
    "sku",
    "qtd_atual",
    "ponto_reposicao",
    "status_reposicao",
    "disponivel_mercado",
    "fornecedor",
    "data_ultima_compra",
    "previsao_entrega",
]:
    if col not in df.columns:
        df[col] = None

# Normaliza tipos base
df["qtd_atual"] = df["qtd_atual"].fillna(0).astype(int)
df["ponto_reposicao"] = df["ponto_reposicao"].fillna(0).astype(int)
df["disponivel_mercado"] = df["disponivel_mercado"].fillna(1).astype(int)
df["status_reposicao"] = df["status_reposicao"].fillna("nao_solicitado")


# Situação e prioridade
def classificar_linha(row):
    if row["qtd_atual"] <= 0 and row["disponivel_mercado"] == 0:
        return "🔴 Sem estoque e sem mercado"
    if row["qtd_atual"] <= row["ponto_reposicao"] and row["disponivel_mercado"] == 0:
        return "🟥 Crítico (mercado ruim)"
    if row["qtd_atual"] <= 0:
        return "🟠 Sem estoque"
    if row["qtd_atual"] <= row["ponto_reposicao"]:
        return "🟡 Baixo"
    return "🟢 OK"


def prioridade(row):
    txt = row["situacao"]
    if "Sem estoque e sem mercado" in txt:
        return 4
    if "Crítico (mercado ruim)" in txt:
        return 3
    if "Sem estoque" in txt:
        return 2
    if "Baixo" in txt:
        return 1
    return 0


df["situacao"] = df.apply(classificar_linha, axis=1)
df["prioridade"] = df.apply(prioridade, axis=1)

# Ordena pelos piores casos primeiro
df = df.sort_values("prioridade", ascending=False)

# KPIs gerais
total_itens = len(df)
estoque_baixo = (df["qtd_atual"] <= df["ponto_reposicao"]).sum()
sem_estoque = (df["qtd_atual"] <= 0).sum()

col1, col2, col3 = st.columns(3)
col1.metric("Itens cadastrados", int(total_itens))
col2.metric("Baixo / crítico", int(estoque_baixo))
col3.metric("Sem estoque", int(sem_estoque))

# ---------- Gráfico de estoque vs ponto de reposição ----------

st.subheader("Visão gráfica de estoque")

if df.empty:
    st.info("Nenhum item cadastrado para exibir no gráfico.")
else:
    chart_df = df.copy().head(30)

    base = alt.Chart(chart_df).encode(
        y=alt.Y("produto:N", sort="-x", title="Produto"),
    )

    barras = base.mark_bar().encode(
        x=alt.X("qtd_atual:Q", title="Quantidade em estoque"),
        color=alt.Color("situacao:N", title="Situação"),
    )

    pontos = base.mark_point(shape="triangle-right", size=80, color="red").encode(
        x=alt.X("ponto_reposicao:Q", title="Ponto de reposição"),
        tooltip=[
            "produto",
            "qtd_atual",
            "ponto_reposicao",
            "situacao",
        ],
    )

    grafico = barras + pontos
    st.altair_chart(grafico, use_container_width=True)

# ---------- Abas ----------

tab_geral, tab_urgentes = st.tabs(["Visão geral", "Urgentes"])

column_config = {
    "disponivel_mercado": st.column_config.CheckboxColumn("Disponível no mercado"),
    "status_reposicao": st.column_config.SelectboxColumn(
        "Status reposição",
        options=["nao_solicitado", "solicitado", "em_transito", "recebido"],
    ),
    "situacao": st.column_config.TextColumn("Situação", disabled=True),
    "prioridade": st.column_config.NumberColumn("Prioridade", disabled=True),
    "fornecedor": st.column_config.TextColumn("Fornecedor"),
    "data_ultima_compra": st.column_config.DateColumn(
        "Última compra",
        format="DD/MM/YYYY",
        default=None,
    ),
    "previsao_entrega": st.column_config.DateColumn(
        "Previsão de entrega",
        format="DD/MM/YYYY",
        default=None,
    ),
}

with tab_geral:
    st.subheader("Todos os produtos")
    edited_df = st.data_editor(
        df,
        num_rows="dynamic",
        hide_index=True,
        column_config=column_config,
        use_container_width=True,
    )

    if st.button("Salvar alterações no banco"):
        save_changes(edited_df)
        st.success("Alterações salvas em estoque.db. Recarregue a página para ver a situação recalculada.")

with tab_urgentes:
    st.subheader("Itens urgentes (prioridade > 0)")
    df_urg = df[df["prioridade"] > 0].copy()

    if df_urg.empty:
        st.info("Nenhum item urgente no momento 😎")
    else:
        colunas_mostrar = [
            "produto",
            "sku",
            "qtd_atual",
            "ponto_reposicao",
            "situacao",
            "status_reposicao",
            "fornecedor",
            "previsao_entrega",
        ]
        st.dataframe(
            df_urg[colunas_mostrar],
            use_container_width=True,
        )
