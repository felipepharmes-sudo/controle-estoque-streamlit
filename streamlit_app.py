import hmac
import sqlite3
from pathlib import Path
from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

# Caminho do banco SQLite
DB_PATH = Path("estoque.db")


# ---------- Autenticação simples (senha única) ----------

def check_password():
    """Retorna True se o usuário digitou a senha correta (ou se não há senha configurada)."""

    # Se não houver senha em st.secrets, libera geral
    if "password" not in st.secrets:
        return True

    def password_entered():
        """Verifica se a senha digitada confere com st.secrets["password"]."""
        if hmac.compare_digest(
            st.session_state["password"], st.secrets["password"]
        ):
            st.session_state["password_ok"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_ok"] = False

    if "password_ok" not in st.session_state:
        # Primeira vez: mostra campo de senha
        st.text_input(
            "Senha", type="password", on_change=password_entered, key="password"
        )
        st.stop()

    if not st.session_state["password_ok"]:
        st.error("Senha incorreta. Tente novamente.")
        st.text_input(
            "Senha", type="password", on_change=password_entered, key="password"
        )
        st.stop()

    return True


# ---------- Funções de banco ----------

def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    """Garante que a tabela exista e, se estiver com colunas antigas, recria o banco."""
    required_cols = [
        "id",
        "produto",
        "sku",
        "categoria",
        "qtd_atual",
        "ponto_reposicao",
        "status_reposicao",
        "disponivel_mercado",
        "fornecedor",
        "data_ultima_compra",
        "previsao_entrega",
        "consumo_diario",
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

            if existing_cols and any(col not in existing_cols for col in required_cols):
                DB_PATH.unlink()  # deleta estoque.db antigo
        except Exception:
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
            categoria TEXT,
            qtd_atual INTEGER,
            ponto_reposicao INTEGER,
            status_reposicao TEXT,
            disponivel_mercado INTEGER,
            fornecedor TEXT,
            data_ultima_compra TEXT,
            previsao_entrega TEXT,
            consumo_diario REAL
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

    if "id" not in df_editado.columns:
        df_editado["id"] = None

    # Normaliza datas para string ISO ou None (evita tipos não suportados) [web:217][web:221]
    def _norm_date(val):
        if pd.isna(val) or val is None:
            return None
        try:
            return pd.to_datetime(val).date().isoformat()
        except Exception:
            return str(val)

    # Linhas que já têm id -> UPDATE
    existentes = df_editado[df_editado["id"].notna()]
    for _, row in existentes.iterrows():
        try:
            id_val = int(row["id"])
        except (TypeError, ValueError):
            continue

        data_compra = _norm_date(row.get("data_ultima_compra"))
        previsao = _norm_date(row.get("previsao_entrega"))

        cur.execute(
            """
            UPDATE produtos SET
                produto = ?,
                sku = ?,
                categoria = ?,
                qtd_atual = ?,
                ponto_reposicao = ?,
                status_reposicao = ?,
                disponivel_mercado = ?,
                fornecedor = ?,
                data_ultima_compra = ?,
                previsao_entrega = ?,
                consumo_diario = ?
            WHERE id = ?
            """,
            (
                row.get("produto"),
                row.get("sku"),
                row.get("categoria"),
                int(row["qtd_atual"]) if pd.notna(row["qtd_atual"]) else None,
                int(row["ponto_reposicao"]) if pd.notna(row["ponto_reposicao"]) else None,
                row.get("status_reposicao") or "nao_solicitado",
                int(row["disponivel_mercado"]) if pd.notna(row["disponivel_mercado"]) else 1,
                row.get("fornecedor"),
                data_compra,
                previsao,
                float(row["consumo_diario"]) if pd.notna(row["consumo_diario"]) else None,
                id_val,
            ),
        )

    # Linhas novas (sem id) -> INSERT
    novos = df_editado[df_editado["id"].isna()]
    for _, row in novos.iterrows():
        data_compra = _norm_date(row.get("data_ultima_compra"))
        previsao = _norm_date(row.get("previsao_entrega"))

        cur.execute(
            """
            INSERT INTO produtos
                (produto, sku, categoria, qtd_atual, ponto_reposicao, status_reposicao,
                 disponivel_mercado, fornecedor, data_ultima_compra, previsao_entrega,
                 consumo_diario)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("produto"),
                row.get("sku"),
                row.get("categoria"),
                int(row["qtd_atual"]) if pd.notna(row["qtd_atual"]) else None,
                int(row["ponto_reposicao"]) if pd.notna(row["ponto_reposicao"]) else None,
                row.get("status_reposicao") or "nao_solicitado",
                int(row["disponivel_mercado"]) if pd.notna(row["disponivel_mercado"]) else 1,
                row.get("fornecedor"),
                data_compra,
                previsao,
                float(row["consumo_diario"]) if pd.notna(row["consumo_diario"]) else None,
            ),
        )

    conn.commit()
    conn.close()


# ---------- App Streamlit ----------

st.set_page_config(page_title="Controle de Estoque", layout="wide")

# Autenticação
check_password()  # bloqueia o app se a senha estiver errada [web:238]

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
                "categoria": "Medicamento",
                "qtd_atual": 5,
                "ponto_reposicao": 10,
                "status_reposicao": "nao_solicitado",
                "disponivel_mercado": 1,
                "fornecedor": "Fornecedor A",
                "data_ultima_compra": None,
                "previsao_entrega": None,
                "consumo_diario": 1.5,
            },
            {
                "id": None,
                "produto": "Exemplo 2",
                "sku": "SKU002",
                "categoria": "Insumo",
                "qtd_atual": 0,
                "ponto_reposicao": 5,
                "status_reposicao": "solicitado",
                "disponivel_mercado": 0,
                "fornecedor": "Fornecedor B",
                "data_ultima_compra": None,
                "previsao_entrega": None,
                "consumo_diario": 0.8,
            },
        ]
    )

# Garante que todas as colunas esperadas existam (se o banco for antigo)
for col in [
    "produto",
    "sku",
    "categoria",
    "qtd_atual",
    "ponto_reposicao",
    "status_reposicao",
    "disponivel_mercado",
    "fornecedor",
    "data_ultima_compra",
    "previsao_entrega",
    "consumo_diario",
]:
    if col not in df.columns:
        df[col] = None

# Normaliza tipos base
df["qtd_atual"] = df["qtd_atual"].fillna(0).astype(int)
df["ponto_reposicao"] = df["ponto_reposicao"].fillna(0).astype(int)
df["disponivel_mercado"] = df["disponivel_mercado"].fillna(1).astype(int)
df["status_reposicao"] = df["status_reposicao"].fillna("nao_solicitado")
df["consumo_diario"] = df["consumo_diario"].fillna(0).astype(float)

# Datas em tipo date (compatível com DateColumn) [web:156]
df["data_ultima_compra"] = pd.to_datetime(
    df["data_ultima_compra"], errors="coerce"
).dt.date
df["previsao_entrega"] = pd.to_datetime(
    df["previsao_entrega"], errors="coerce"
).dt.date

# Situação, prioridade e previsão de ruptura
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


def dias_estoque(row):
    if row["consumo_diario"] and row["consumo_diario"] > 0:
        return row["qtd_atual"] / row["consumo_diario"]
    return None


def data_ruptura(row):
    if row["dias_estoque"] and row["dias_estoque"] > 0:
        return date.today() + timedelta(days=int(row["dias_estoque"]))
    return None


df["situacao"] = df.apply(classificar_linha, axis=1)
df["prioridade"] = df.apply(prioridade, axis=1)
df["dias_estoque"] = df.apply(dias_estoque, axis=1)
df["data_ruptura_prevista"] = df.apply(data_ruptura, axis=1)

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

# Configuração das colunas da tabela (inclui DateColumn com date picker e campos de negócio) [web:156][web:161]
column_config = {
    "disponivel_mercado": st.column_config.CheckboxColumn("Disponível no mercado"),
    "status_reposicao": st.column_config.SelectboxColumn(
        "Status reposição",
        options=["nao_solicitado", "solicitado", "em_transito", "recebido"],
    ),
    "situacao": st.column_config.TextColumn("Situação", disabled=True),
    "prioridade": st.column_config.NumberColumn("Prioridade", disabled=True),
    "categoria": st.column_config.TextColumn("Categoria"),
    "fornecedor": st.column_config.TextColumn("Fornecedor"),
    "consumo_diario": st.column_config.NumberColumn(
        "Consumo diário (unid/dia)", format="%.2f"
    ),
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
    "dias_estoque": st.column_config.NumberColumn(
        "Dias de estoque (estimado)", disabled=True, format="%.1f"
    ),
    "data_ruptura_prevista": st.column_config.DateColumn(
        "Data ruptura (estimada)", disabled=True, format="DD/MM/YYYY"
    ),
}

@st.cache_data
def df_to_csv(dataframe: pd.DataFrame) -> bytes:
    """Converte DataFrame para CSV em bytes, pronto para download_button."""  # [web:232][web:226]
    return dataframe.to_csv(index=False).encode("utf-8")


with tab_geral:
    st.subheader("Filtros")

    colf1, colf2 = st.columns(2)
    op_forn = ["Todos"] + sorted(
        [f for f in df["fornecedor"].dropna().unique().tolist() if f != ""]
    )
    op_cat = ["Todos"] + sorted(
        [c for c in df["categoria"].dropna().unique().tolist() if c != ""]
    )

    filtro_forn = colf1.selectbox("Fornecedor", op_forn)
    filtro_cat = colf2.selectbox("Categoria", op_cat)

    df_view = df.copy()
    if filtro_forn != "Todos":
        df_view = df_view[df_view["fornecedor"] == filtro_forn]
    if filtro_cat != "Todos":
        df_view = df_view[df_view["categoria"] == filtro_cat]

    st.subheader("Todos os produtos (editável)")

    edited_df = st.data_editor(
        df_view,
        num_rows="dynamic",
        hide_index=True,
        column_config=column_config,
        use_container_width=True,
    )

    colb1, colb2 = st.columns(2)
    if colb1.button("Salvar alterações no banco"):
        save_changes(edited_df)
        st.success("Alterações salvas em estoque.db. Recarregue a página para ver a situação recalculada.")

    # Download CSV da visão atual
    csv_all = df_to_csv(df_view)
    colb2.download_button(
        "Baixar visão atual (CSV)",
        data=csv_all,
        file_name="estoque_visao_atual.csv",
        mime="text/csv",
    )

with tab_urgentes:
    st.subheader("Itens urgentes (prioridade > 0)")
    df_urg = df[df["prioridade"] > 0].copy()

    if df_urg.empty:
        st.info("Nenhum item urgente no momento 😎")
    else:
        colunas_mostrar = [
            "produto",
            "sku",
            "categoria",
            "qtd_atual",
            "ponto_reposicao",
            "situacao",
            "status_reposicao",
            "fornecedor",
            "consumo_diario",
            "dias_estoque",
            "data_ruptura_prevista",
            "previsao_entrega",
        ]
        st.dataframe(
            df_urg[colunas_mostrar],
            use_container_width=True,
        )

        csv_urg = df_to_csv(df_urg[colunas_mostrar])
        st.download_button(
            "Baixar urgentes (CSV)",
            data=csv_urg,
            file_name="estoque_urgentes.csv",
            mime="text/csv",
        )
