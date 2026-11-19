"""
ETL — Extração, Transformação e Carga da base Mercatto.

Entrada : data/raw/*.csv        (dados brutos, com problemas de qualidade)
Saída   : data/processed/bi.db  (SQLite, modelo estrela com PK/FK)
          data/processed/*.csv  (mesmas tabelas, para uso no Power BI/Excel)
          reports/log_etl.json  (o que foi tratado em cada etapa)

Modelo estrela (granularidade da fato principal = 1 linha por item de pedido):
    dim_cliente, dim_produto, dim_loja, dim_calendario
    fato_pedido        (1 linha por pedido)
    fato_item_pedido   (1 linha por produto dentro do pedido)

Execução:
    python -m src.etl
"""
from __future__ import annotations

import json
import sqlite3
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
RAW = RAIZ / "data" / "raw"
PROC = RAIZ / "data" / "processed"
REPORTS = RAIZ / "reports"
DB_PATH = PROC / "bi.db"
DATA_REFERENCIA = pd.Timestamp("2025-12-31")  # data de "fechamento" da análise

# Tabela de domínio (IBGE): UF -> região
UF_REGIAO = {
    "SP": "Sudeste", "RJ": "Sudeste", "MG": "Sudeste", "ES": "Sudeste",
    "BA": "Nordeste", "PE": "Nordeste", "CE": "Nordeste", "MA": "Nordeste", "RN": "Nordeste",
    "PB": "Nordeste", "AL": "Nordeste", "SE": "Nordeste", "PI": "Nordeste",
    "PR": "Sul", "RS": "Sul", "SC": "Sul",
    "DF": "Centro-Oeste", "GO": "Centro-Oeste", "MT": "Centro-Oeste", "MS": "Centro-Oeste",
    "PA": "Norte", "AM": "Norte", "TO": "Norte", "AC": "Norte", "AP": "Norte", "RO": "Norte", "RR": "Norte",
}
STATUS_VALIDOS = {"Entregue", "Cancelado", "Devolvido"}
QTD_MAXIMA_PLAUSIVEL = 20  # varejo B2C: acima disso é tratado como erro de digitação

DDL = """
PRAGMA foreign_keys = ON;
DROP TABLE IF EXISTS fato_item_pedido;
DROP TABLE IF EXISTS fato_pedido;
DROP TABLE IF EXISTS dim_cliente;
DROP TABLE IF EXISTS dim_produto;
DROP TABLE IF EXISTS dim_loja;
DROP TABLE IF EXISTS dim_calendario;

CREATE TABLE dim_calendario (
    data TEXT PRIMARY KEY, ano INTEGER, mes INTEGER, nome_mes TEXT, trimestre INTEGER,
    ano_mes TEXT, dia_semana INTEGER, nome_dia_semana TEXT, fim_de_semana INTEGER,
    evento_comercial TEXT
);
CREATE TABLE dim_cliente (
    id_cliente INTEGER PRIMARY KEY, cidade TEXT, uf TEXT, regiao TEXT, idade INTEGER,
    faixa_etaria TEXT, data_cadastro TEXT, ano_cadastro INTEGER, canal_aquisicao TEXT
);
CREATE TABLE dim_produto (
    id_produto INTEGER PRIMARY KEY, nome_produto TEXT, categoria TEXT, marca TEXT, linha TEXT,
    preco_lista REAL, custo_unitario REAL, margem_lista_pct REAL, custo_imputado INTEGER
);
CREATE TABLE dim_loja (
    id_loja INTEGER PRIMARY KEY, nome_loja TEXT, tipo_loja TEXT, canal TEXT, cidade TEXT, uf TEXT,
    regiao TEXT, data_abertura TEXT
);
CREATE TABLE fato_pedido (
    id_pedido INTEGER PRIMARY KEY,
    id_cliente INTEGER NOT NULL REFERENCES dim_cliente(id_cliente),
    id_loja INTEGER NOT NULL REFERENCES dim_loja(id_loja),
    data_pedido TEXT NOT NULL REFERENCES dim_calendario(data),
    canal TEXT, forma_pagamento TEXT, status TEXT, valor_frete REAL,
    qtd_itens INTEGER, receita_bruta REAL, valor_desconto REAL, receita_liquida REAL,
    custo_total REAL, margem_bruta REAL
);
CREATE TABLE fato_item_pedido (
    id_item INTEGER PRIMARY KEY,
    id_pedido INTEGER NOT NULL REFERENCES fato_pedido(id_pedido),
    id_produto INTEGER NOT NULL REFERENCES dim_produto(id_produto),
    quantidade INTEGER, preco_unitario REAL, desconto_pct REAL,
    receita_bruta REAL, valor_desconto REAL, receita_liquida REAL, custo_total REAL, margem_bruta REAL
);
CREATE INDEX ix_pedido_data ON fato_pedido(data_pedido);
CREATE INDEX ix_pedido_cliente ON fato_pedido(id_cliente);
CREATE INDEX ix_item_pedido ON fato_item_pedido(id_pedido);

-- Visão analítica "larga" usada pelo dashboard e pela análise
DROP VIEW IF EXISTS vw_vendas;
CREATE VIEW vw_vendas AS
SELECT i.id_item, i.id_pedido, p.data_pedido, cal.ano, cal.mes, cal.ano_mes, cal.evento_comercial,
       p.status, p.canal, p.forma_pagamento, l.id_loja, l.nome_loja, l.regiao AS regiao_loja,
       c.id_cliente, c.regiao AS regiao_cliente, c.uf AS uf_cliente, c.faixa_etaria,
       pr.id_produto, pr.nome_produto, pr.categoria, pr.linha,
       i.quantidade, i.preco_unitario, i.desconto_pct, i.receita_bruta, i.valor_desconto,
       i.receita_liquida, i.custo_total, i.margem_bruta
FROM fato_item_pedido i
JOIN fato_pedido p   ON p.id_pedido = i.id_pedido
JOIN dim_calendario cal ON cal.data = p.data_pedido
JOIN dim_loja l      ON l.id_loja = p.id_loja
JOIN dim_cliente c   ON c.id_cliente = p.id_cliente
JOIN dim_produto pr  ON pr.id_produto = i.id_produto;
"""


# --------------------------------------------------------------------------
# Funções de limpeza reutilizáveis
# --------------------------------------------------------------------------
def chave_texto(s: pd.Series) -> pd.Series:
    """Chave de comparação: sem acento, minúscula e sem espaços nas pontas."""
    return s.astype("string").str.strip().map(
        lambda x: unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode().lower()
        if pd.notna(x) else x)


def padronizar_por_moda(s: pd.Series) -> pd.Series:
    """Unifica variações de escrita ('SÃO PAULO', 'sao paulo') na forma mais frequente."""
    chave = chave_texto(s)
    forma_canonica = (pd.DataFrame({"chave": chave, "valor": s.astype("string").str.strip()})
                      .groupby("chave")["valor"].agg(lambda v: v.value_counts().index[0]))
    return chave.map(forma_canonica)


def para_numero(s: pd.Series) -> pd.Series:
    """Converte '1.299,90' (BR) e '1299.9' (padrão) para float."""
    txt = s.astype("string").str.strip()
    br = txt.str.contains(",", na=False)
    txt = txt.where(~br, txt.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    return pd.to_numeric(txt, errors="coerce")


def para_data(s: pd.Series) -> pd.Series:
    """Aceita 'AAAA-MM-DD' e 'DD/MM/AAAA'."""
    iso = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
    br = pd.to_datetime(s, format="%d/%m/%Y", errors="coerce")
    return iso.fillna(br)


def remover_duplicadas(df: pd.DataFrame, pk: str, log: dict, nome: str) -> pd.DataFrame:
    n0 = len(df)
    df = df.drop_duplicates()
    log[f"{nome}_duplicatas_exatas_removidas"] = n0 - len(df)
    n1 = len(df)
    df = df.drop_duplicates(subset=pk, keep="first")
    log[f"{nome}_pk_repetida_removida"] = n1 - len(df)
    return df


# --------------------------------------------------------------------------
# Transformações por tabela
# --------------------------------------------------------------------------
def tratar_clientes(df: pd.DataFrame, log: dict) -> pd.DataFrame:
    df = remover_duplicadas(df, "id_cliente", log, "clientes")

    uf_antes = df["uf"].copy()
    df["uf"] = df["uf"].astype("string").str.strip().str.upper()
    log["clientes_uf_padronizada"] = int((uf_antes != df["uf"]).sum())
    log["clientes_uf_invalida"] = int((~df["uf"].isin(list(UF_REGIAO))).sum())

    cid_antes = df["cidade"].copy()
    df["cidade"] = padronizar_por_moda(df["cidade"])
    log["clientes_cidade_padronizada"] = int((cid_antes != df["cidade"]).sum())

    df["regiao"] = df["uf"].map(UF_REGIAO)

    nasc = para_data(df["data_nascimento"])
    idade = ((DATA_REFERENCIA - nasc).dt.days / 365.25)
    invalida = idade.notna() & ~idade.between(16, 100)
    log["clientes_nascimento_nulo"] = int(nasc.isna().sum())
    log["clientes_nascimento_invalido_anulado"] = int(invalida.sum())
    idade = idade.mask(invalida)
    df["idade"] = np.floor(idade).astype("Int64")
    df["faixa_etaria"] = pd.cut(idade, [15, 24, 34, 44, 54, 64, 120],
                                labels=["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
                                ).astype("string").fillna("Não informado")

    df["data_cadastro"] = para_data(df["data_cadastro"])
    df["ano_cadastro"] = df["data_cadastro"].dt.year

    # Privacidade (LGPD — minimização): nome, e-mail e data de nascimento exata
    # não são necessários para a análise e NÃO seguem para a camada analítica.
    log["clientes_email_nulo_na_origem"] = int(df["email"].isna().sum())
    log["clientes_campos_pessoais_removidos"] = ["nome", "email", "data_nascimento"]
    df["data_cadastro"] = df["data_cadastro"].dt.strftime("%Y-%m-%d")
    return df[["id_cliente", "cidade", "uf", "regiao", "idade", "faixa_etaria",
               "data_cadastro", "ano_cadastro", "canal_aquisicao"]]


def tratar_produtos(df: pd.DataFrame, log: dict) -> pd.DataFrame:
    df = remover_duplicadas(df, "id_produto", log, "produtos")

    cat_antes = df["categoria"].copy()
    df["categoria"] = padronizar_por_moda(df["categoria"])
    log["produtos_categoria_padronizada"] = int((cat_antes != df["categoria"]).sum())

    brasileiro = df["preco_lista"].astype("string").str.contains(",", na=False)
    df["preco_lista"] = para_numero(df["preco_lista"])
    log["produtos_preco_convertido_de_formato_br"] = int(brasileiro.sum())

    df["custo_unitario"] = pd.to_numeric(df["custo_unitario"], errors="coerce")
    nulo = df["custo_unitario"].isna()
    # Imputação: custo = preço x (1 - margem mediana da categoria)
    margem_cat = (1 - df["custo_unitario"] / df["preco_lista"]).groupby(df["categoria"]).median()
    df.loc[nulo, "custo_unitario"] = (df.loc[nulo, "preco_lista"]
                                      * (1 - df.loc[nulo, "categoria"].map(margem_cat))).round(2)
    df["custo_imputado"] = nulo.astype(int)
    log["produtos_custo_imputado_pela_margem_mediana_da_categoria"] = int(nulo.sum())

    df["margem_lista_pct"] = (1 - df["custo_unitario"] / df["preco_lista"]).round(4)
    return df[["id_produto", "nome_produto", "categoria", "marca", "linha", "preco_lista",
               "custo_unitario", "margem_lista_pct", "custo_imputado"]]


def tratar_lojas(df: pd.DataFrame, log: dict) -> pd.DataFrame:
    df = remover_duplicadas(df, "id_loja", log, "lojas")
    df["canal"] = np.where(df["tipo_loja"] == "Online", "Online", "Loja física")
    return df[["id_loja", "nome_loja", "tipo_loja", "canal", "cidade", "uf", "regiao", "data_abertura"]]


def tratar_pedidos(df: pd.DataFrame, clientes: pd.DataFrame, lojas: pd.DataFrame, log: dict) -> pd.DataFrame:
    df = remover_duplicadas(df, "id_pedido", log, "pedidos")

    br = df["data_pedido"].astype("string").str.contains("/", na=False)
    df["data_pedido"] = para_data(df["data_pedido"])
    log["pedidos_data_convertida_de_dd_mm_aaaa"] = int(br.sum())
    log["pedidos_data_invalida_removida"] = int(df["data_pedido"].isna().sum())
    df = df[df["data_pedido"].notna()]

    st_antes = df["status"].copy()
    df["status"] = df["status"].astype("string").str.strip().str.capitalize()
    log["pedidos_status_padronizado"] = int((st_antes != df["status"]).sum())
    log["pedidos_status_invalido_removido"] = int((~df["status"].isin(STATUS_VALIDOS)).sum())
    df = df[df["status"].isin(STATUS_VALIDOS)]

    neg = df["valor_frete"] < 0
    df.loc[neg, "valor_frete"] = df.loc[neg, "valor_frete"].abs()
    log["pedidos_frete_negativo_corrigido_abs"] = int(neg.sum())

    orfao_cli = ~df["id_cliente"].isin(clientes["id_cliente"])
    orfao_loja = ~df["id_loja"].isin(lojas["id_loja"])
    log["pedidos_cliente_inexistente_removidos"] = int(orfao_cli.sum())
    log["pedidos_loja_inexistente_removidos"] = int(orfao_loja.sum())
    df = df[~orfao_cli & ~orfao_loja]

    df = df.merge(lojas[["id_loja", "canal"]], on="id_loja", how="left")
    return df


def tratar_itens(df: pd.DataFrame, pedidos: pd.DataFrame, produtos: pd.DataFrame, log: dict) -> pd.DataFrame:
    df = remover_duplicadas(df, "id_item", log, "itens")

    df["quantidade"] = pd.to_numeric(df["quantidade"], errors="coerce")
    invalida = df["quantidade"].isna() | (df["quantidade"] <= 0)
    outlier = df["quantidade"] > QTD_MAXIMA_PLAUSIVEL
    log["itens_quantidade_zero_negativa_removidos"] = int(invalida.sum())
    log[f"itens_quantidade_acima_de_{QTD_MAXIMA_PLAUSIVEL}_removidos"] = int(outlier.sum())
    df = df[~invalida & ~outlier]

    texto = df["desconto_pct"].astype("string").str.contains("%", na=False)
    desc = pd.to_numeric(df["desconto_pct"].astype("string").str.replace("%", "", regex=False)
                         .str.strip(), errors="coerce")
    escala_100 = desc > 1
    desc = desc.where(~escala_100, desc / 100)
    log["itens_desconto_convertido_de_texto_ou_escala_100"] = int((texto | escala_100).sum())
    df["desconto_pct"] = desc.fillna(0).clip(0, 0.9)

    df["preco_unitario"] = pd.to_numeric(df["preco_unitario"], errors="coerce")
    nulo = df["preco_unitario"].isna()
    df.loc[nulo, "preco_unitario"] = df.loc[nulo, "id_produto"].map(
        produtos.set_index("id_produto")["preco_lista"])
    log["itens_preco_nulo_imputado_com_preco_de_lista"] = int(nulo.sum())

    orfao_ped = ~df["id_pedido"].isin(pedidos["id_pedido"])
    orfao_prod = ~df["id_produto"].isin(produtos["id_produto"])
    log["itens_de_pedidos_removidos_ou_inexistentes"] = int(orfao_ped.sum())
    log["itens_produto_inexistente_removidos"] = int(orfao_prod.sum())
    df = df[~orfao_ped & ~orfao_prod].copy()

    # Métricas derivadas
    custo = df["id_produto"].map(produtos.set_index("id_produto")["custo_unitario"])
    df["quantidade"] = df["quantidade"].astype(int)
    df["receita_bruta"] = (df["quantidade"] * df["preco_unitario"]).round(2)
    df["valor_desconto"] = (df["receita_bruta"] * df["desconto_pct"]).round(2)
    df["receita_liquida"] = (df["receita_bruta"] - df["valor_desconto"]).round(2)
    df["custo_total"] = (df["quantidade"] * custo).round(2)
    df["margem_bruta"] = (df["receita_liquida"] - df["custo_total"]).round(2)
    return df


def agregar_pedidos(pedidos: pd.DataFrame, itens: pd.DataFrame, log: dict) -> pd.DataFrame:
    tot = itens.groupby("id_pedido").agg(
        qtd_itens=("quantidade", "sum"), receita_bruta=("receita_bruta", "sum"),
        valor_desconto=("valor_desconto", "sum"), receita_liquida=("receita_liquida", "sum"),
        custo_total=("custo_total", "sum"), margem_bruta=("margem_bruta", "sum")).round(2)
    sem_itens = ~pedidos["id_pedido"].isin(tot.index)
    log["pedidos_sem_itens_validos_removidos"] = int(sem_itens.sum())
    pedidos = pedidos[~sem_itens].merge(tot, left_on="id_pedido", right_index=True)
    pedidos["data_pedido"] = pedidos["data_pedido"].dt.strftime("%Y-%m-%d")
    return pedidos[["id_pedido", "id_cliente", "id_loja", "data_pedido", "canal", "forma_pagamento",
                    "status", "valor_frete", "qtd_itens", "receita_bruta", "valor_desconto",
                    "receita_liquida", "custo_total", "margem_bruta"]]


def criar_calendario(inicio: pd.Timestamp, fim: pd.Timestamp) -> pd.DataFrame:
    dias = pd.date_range(inicio, fim, freq="D")
    nomes_mes = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
    nomes_dia = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    cal = pd.DataFrame({"data": dias})
    cal["ano"] = dias.year
    cal["mes"] = dias.month
    cal["nome_mes"] = [nomes_mes[m - 1] for m in dias.month]
    cal["trimestre"] = dias.quarter
    cal["ano_mes"] = dias.strftime("%Y-%m")
    cal["dia_semana"] = dias.day_of_week + 1
    cal["nome_dia_semana"] = [nomes_dia[d] for d in dias.day_of_week]
    cal["fim_de_semana"] = (dias.day_of_week >= 5).astype(int)

    evento = pd.Series("Nenhum", index=dias)
    for ano in sorted(set(dias.year)):
        evento[(dias >= pd.Timestamp(ano, 12, 1)) & (dias <= pd.Timestamp(ano, 12, 24))] = "Natal"
        # Black Friday: sexta após a 4ª quinta de novembro, até a Cyber Monday (tem prioridade sobre Natal)
        nov1 = pd.Timestamp(year=ano, month=11, day=1)
        bf = nov1 + pd.Timedelta(days=(3 - nov1.day_of_week) % 7 + 22)
        evento[(dias >= bf) & (dias <= bf + pd.Timedelta(days=3))] = "Black Friday"
        for mes, nome in ((5, "Dia das Mães"), (8, "Dia dos Pais")):  # 2º domingo, semana anterior
            d1 = pd.Timestamp(year=ano, month=mes, day=1)
            domingo = d1 + pd.Timedelta(days=(6 - d1.day_of_week) % 7 + 7)
            evento[(dias >= domingo - pd.Timedelta(days=7)) & (dias <= domingo)] = nome
    cal["evento_comercial"] = evento.to_numpy()
    cal["data"] = cal["data"].dt.strftime("%Y-%m-%d")
    return cal


# --------------------------------------------------------------------------
def main(raw: Path = RAW, proc: Path = PROC) -> dict:
    proc.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    log: dict = {}

    # 1) EXTRAÇÃO
    brutos = {n: pd.read_csv(raw / f"{n}.csv", dtype=str if n in ("produtos", "itens_pedido") else None)
              for n in ("clientes", "produtos", "lojas", "pedidos", "itens_pedido")}
    log["linhas_lidas"] = {n: len(df) for n, df in brutos.items()}
    for col in ("id_produto",):
        brutos["produtos"][col] = brutos["produtos"][col].astype(int)
    for col in ("id_item", "id_pedido", "id_produto"):
        brutos["itens_pedido"][col] = brutos["itens_pedido"][col].astype(int)

    # 2) TRANSFORMAÇÃO
    clientes = tratar_clientes(brutos["clientes"], log)
    produtos = tratar_produtos(brutos["produtos"], log)
    lojas = tratar_lojas(brutos["lojas"], log)
    pedidos = tratar_pedidos(brutos["pedidos"], clientes, lojas, log)
    itens = tratar_itens(brutos["itens_pedido"], pedidos, produtos, log)
    pedidos = agregar_pedidos(pedidos, itens, log)
    itens = itens[itens["id_pedido"].isin(pedidos["id_pedido"])]
    itens = itens[["id_item", "id_pedido", "id_produto", "quantidade", "preco_unitario", "desconto_pct",
                   "receita_bruta", "valor_desconto", "receita_liquida", "custo_total", "margem_bruta"]]
    calendario = criar_calendario(pd.Timestamp(pedidos["data_pedido"].min()),
                                  pd.Timestamp(pedidos["data_pedido"].max()))

    tabelas = {"dim_calendario": calendario, "dim_cliente": clientes, "dim_produto": produtos,
               "dim_loja": lojas, "fato_pedido": pedidos, "fato_item_pedido": itens}
    log["linhas_carregadas"] = {n: len(df) for n, df in tabelas.items()}

    # 3) CARGA (SQLite com chaves e CSV tratados)
    if DB_PATH.exists():
        DB_PATH.unlink()
    with sqlite3.connect(DB_PATH) as con:
        con.executescript(DDL)
        for nome, df in tabelas.items():
            df.to_sql(nome, con, if_exists="append", index=False)
            df.to_csv(proc / f"{nome}.csv", index=False, encoding="utf-8-sig")
        con.commit()

    (REPORTS / "log_etl.json").write_text(json.dumps(log, indent=2, ensure_ascii=False, default=int),
                                          encoding="utf-8")
    return log


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, ensure_ascii=False, default=int))
