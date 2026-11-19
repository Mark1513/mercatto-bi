"""
Análise de dados e técnicas analíticas — Mercatto.

1. KPIs (com as fórmulas documentadas em docs/01_planejamento.md)
2. Segmentação de clientes: RFM + K-means (escolha de k por cotovelo e silhouette)
3. Previsão da receita mensal: Holt-Winters x baseline sazonal ingênuo (MAPE)
4. Detecção de anomalias na receita diária (z-score robusto)

Os resultados são gravados no próprio bi.db (tabelas an_*) e em
reports/resultados_analise.json, e são consumidos pelo dashboard.

Execução:
    python -m src.analise
"""
from __future__ import annotations

import json
import sqlite3
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
from statsmodels.tsa.holtwinters import ExponentialSmoothing

RAIZ = Path(__file__).resolve().parents[1]
DB_PATH = RAIZ / "data" / "processed" / "bi.db"
REPORTS = RAIZ / "reports"
DATA_REFERENCIA = pd.Timestamp("2025-12-31")
SEED = 42


# --------------------------------------------------------------------------
# Carga
# --------------------------------------------------------------------------
def conectar(db: Path = DB_PATH) -> sqlite3.Connection:
    return sqlite3.connect(db)


def carregar_vendas(con) -> pd.DataFrame:
    """Visão item a item (vw_vendas) com datas convertidas."""
    df = pd.read_sql("SELECT * FROM vw_vendas", con, parse_dates=["data_pedido"])
    return df


def carregar_pedidos(con) -> pd.DataFrame:
    df = pd.read_sql(
        "SELECT p.*, c.regiao AS regiao_cliente, c.faixa_etaria, cal.ano, cal.ano_mes, cal.evento_comercial "
        "FROM fato_pedido p JOIN dim_cliente c USING(id_cliente) "
        "JOIN dim_calendario cal ON cal.data = p.data_pedido", con, parse_dates=["data_pedido"])
    return df


# --------------------------------------------------------------------------
# 1. KPIs
# --------------------------------------------------------------------------
def calcular_kpis(pedidos: pd.DataFrame) -> dict:
    """KPIs de nível pedido. 'Faturados' = Entregue + Devolvido (saíram para o cliente)."""
    ent = pedidos[pedidos["status"] == "Entregue"]
    faturados = pedidos[pedidos["status"].isin(["Entregue", "Devolvido"])]
    receita = ent["receita_liquida"].sum()
    compras_por_cliente = ent.groupby("id_cliente").size()
    return {
        "receita_liquida": receita,
        "margem_bruta": ent["margem_bruta"].sum(),
        "margem_bruta_pct": ent["margem_bruta"].sum() / receita if receita else np.nan,
        "pedidos_entregues": len(ent),
        "ticket_medio": receita / len(ent) if len(ent) else np.nan,
        "desconto_medio_pct": ent["valor_desconto"].sum() / ent["receita_bruta"].sum() if len(ent) else np.nan,
        "taxa_devolucao_pct": (faturados["status"] == "Devolvido").mean() if len(faturados) else np.nan,
        "taxa_cancelamento_pct": (pedidos["status"] == "Cancelado").mean() if len(pedidos) else np.nan,
        "participacao_online_pct": ent.loc[ent["canal"] == "Online", "receita_liquida"].sum() / receita
        if receita else np.nan,
        "clientes_ativos": int(ent["id_cliente"].nunique()),
        "taxa_recompra_pct": (compras_por_cliente >= 2).mean() if len(compras_por_cliente) else np.nan,
    }


def kpis_por_ano(pedidos: pd.DataFrame) -> pd.DataFrame:
    linhas = [{"ano": a, **calcular_kpis(g)} for a, g in pedidos.groupby("ano")]
    df = pd.DataFrame(linhas).set_index("ano")
    df["crescimento_receita_pct"] = df["receita_liquida"].pct_change()
    return df


# --------------------------------------------------------------------------
# 2. Segmentação RFM + K-means
# --------------------------------------------------------------------------
def tabela_rfm(pedidos: pd.DataFrame, data_ref: pd.Timestamp = DATA_REFERENCIA) -> pd.DataFrame:
    ent = pedidos[pedidos["status"] == "Entregue"]
    rfm = ent.groupby("id_cliente").agg(
        ultima_compra=("data_pedido", "max"),
        frequencia=("id_pedido", "count"),
        monetario=("receita_liquida", "sum"))
    rfm["recencia_dias"] = (data_ref - rfm["ultima_compra"]).dt.days
    return rfm[["recencia_dias", "frequencia", "monetario"]]


def escolher_k(X: np.ndarray, ks=range(2, 9)) -> pd.DataFrame:
    linhas = []
    for k in ks:
        km = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit(X)
        linhas.append({"k": k, "inercia": km.inertia_,
                       "silhouette": silhouette_score(X, km.labels_, sample_size=5000, random_state=SEED)})
    return pd.DataFrame(linhas)


def nomear_segmentos(perfil: pd.DataFrame) -> dict:
    """Dá nomes de negócio aos clusters a partir dos centróides (médias de R, F e M)."""
    nomes = {}
    recentes = perfil[perfil["recencia_dias"] <= 180]   # compraram nos últimos ~6 meses
    antigos = perfil[perfil["recencia_dias"] > 180]
    for grupo, nome_topo, nome_resto in ((recentes, "Campeões", None), (antigos, "Em risco", "Hibernando")):
        if grupo.empty:
            continue
        topo = grupo["monetario"].idxmax()
        nomes[topo] = nome_topo
        for cid, r in grupo.drop(index=topo).iterrows():
            if nome_resto:
                nomes[cid] = nome_resto
            else:
                nomes[cid] = "Regulares" if r["frequencia"] >= 3 else "Novos"
    # garante nomes únicos
    vistos: dict = {}
    for cid in sorted(nomes, key=lambda c: -perfil.loc[c, "monetario"]):
        n = nomes[cid]
        vistos[n] = vistos.get(n, 0) + 1
        if vistos[n] > 1:
            nomes[cid] = f"{n} ({vistos[n]})"
    return nomes


def segmentar_clientes(pedidos: pd.DataFrame, k: int | None = None):
    rfm = tabela_rfm(pedidos)
    # log reduz a assimetria de F e M; padronização evita que M domine a distância
    X = StandardScaler().fit_transform(np.log1p(rfm[["recencia_dias", "frequencia", "monetario"]]))
    avaliacao = escolher_k(X)
    if k is None:  # melhor silhouette entre 3 e 6 grupos (faixa acionável para o negócio)
        faixa = avaliacao[avaliacao["k"].between(3, 6)]
        k = int(faixa.loc[faixa["silhouette"].idxmax(), "k"])
    km = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit(X)
    rfm["cluster"] = km.labels_
    perfil = rfm.groupby("cluster")[["recencia_dias", "frequencia", "monetario"]].mean()
    nomes = nomear_segmentos(perfil)
    rfm["segmento"] = rfm["cluster"].map(nomes)
    resumo = rfm.groupby("segmento").agg(
        clientes=("cluster", "size"), recencia_media=("recencia_dias", "mean"),
        frequencia_media=("frequencia", "mean"), monetario_medio=("monetario", "mean"),
        receita_total=("monetario", "sum"))
    resumo["pct_clientes"] = resumo["clientes"] / resumo["clientes"].sum()
    resumo["pct_receita"] = resumo["receita_total"] / resumo["receita_total"].sum()
    resumo = resumo.sort_values("receita_total", ascending=False)
    sil = float(avaliacao.loc[avaliacao["k"] == k, "silhouette"].iloc[0])
    return rfm.reset_index(), resumo.reset_index(), avaliacao, k, sil


# --------------------------------------------------------------------------
# 3. Previsão da receita mensal
# --------------------------------------------------------------------------
def serie_mensal(pedidos: pd.DataFrame) -> pd.Series:
    ent = pedidos[pedidos["status"] == "Entregue"]
    s = ent.set_index("data_pedido")["receita_liquida"].resample("MS").sum()
    s.index.freq = "MS"
    return s


def mape(real, prev) -> float:
    real, prev = np.asarray(real), np.asarray(prev)
    return float(np.mean(np.abs((real - prev) / real)))


def _hw(serie: pd.Series, trend: str, seasonal: str, log: bool = False):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        y = np.log(serie) if log else serie
        return ExponentialSmoothing(y, trend=trend, seasonal=seasonal, seasonal_periods=12,
                                    initialization_method="estimated").fit(optimized=True)


def _prever(nome: str, treino: pd.Series, h: int) -> np.ndarray:
    """Prevê h meses à frente com o modelo candidato 'nome'."""
    if nome == "Holt-Winters (tendência aditiva, sazonalidade multiplicativa)":
        return _hw(treino, "add", "mul").forecast(h).to_numpy()
    if nome == "Holt-Winters em log (crescimento e sazonalidade proporcionais)":
        return np.exp(_hw(treino, "add", "add", log=True).forecast(h).to_numpy())
    if nome == "Sazonal ingênuo c/ crescimento (baseline)":
        cresc = treino.iloc[-12:].sum() / treino.iloc[-24:-12].sum()
        return treino.iloc[-12:].to_numpy()[:h] * cresc  # mesmo mês do ano anterior x crescimento
    raise ValueError(nome)


CANDIDATOS = ["Holt-Winters (tendência aditiva, sazonalidade multiplicativa)",
              "Holt-Winters em log (crescimento e sazonalidade proporcionais)",
              "Sazonal ingênuo c/ crescimento (baseline)"]


def validar_origem_movel(s: pd.Series, h: int = 3, treino_minimo: int = 24) -> pd.DataFrame:
    """Backtest: treina até o mês t, prevê t+1..t+h, avança 1 mês e repete."""
    linhas = []
    for fim in range(treino_minimo, len(s) - h + 1):
        treino, teste = s.iloc[:fim], s.iloc[fim:fim + h]
        for nome in CANDIDATOS:
            prev = _prever(nome, treino, h)
            linhas.append({"modelo": nome, "origem": treino.index[-1].strftime("%Y-%m"),
                           "MAPE": mape(teste, prev), "MAE": float(np.mean(np.abs(teste.to_numpy() - prev)))})
    return pd.DataFrame(linhas)


def prever_receita(pedidos: pd.DataFrame, horizonte: int = 6):
    s = serie_mensal(pedidos)
    backtest = validar_origem_movel(s)
    metricas = (backtest.groupby("modelo")
                .agg(MAPE=("MAPE", "mean"), MAPE_desvio=("MAPE", "std"), MAE=("MAE", "mean"),
                     janelas=("MAPE", "size"))
                .sort_values("MAPE").reset_index())
    melhor = metricas.iloc[0]["modelo"]
    metricas["escolhido"] = metricas["modelo"] == melhor

    # Previsão "fora da amostra" dos últimos 6 meses (para visualizar o erro no gráfico)
    teste = s.iloc[-6:]
    prev_teste = _prever(melhor, s.iloc[:-6], 6)

    # Reajuste com a série completa e previsão do horizonte futuro
    futuro_idx = pd.date_range(s.index[-1] + pd.offsets.MonthBegin(), periods=horizonte, freq="MS")
    futuro = _prever(melhor, s, horizonte)
    # Intervalo aproximado de 95% a partir do erro percentual observado no backtest
    erro = float(backtest.loc[backtest["modelo"] == melhor, "MAPE"].mean())
    tabela = pd.concat([
        pd.DataFrame({"mes": s.index, "real": s.values, "previsto": np.nan, "tipo": "histórico"}),
        pd.DataFrame({"mes": teste.index, "real": teste.values, "previsto": prev_teste,
                      "tipo": "teste (fora da amostra)"}),
        pd.DataFrame({"mes": futuro_idx, "real": np.nan, "previsto": futuro, "tipo": "previsão"}),
    ], ignore_index=True)
    eh_prev = tabela["tipo"] == "previsão"
    tabela["limite_inferior"] = np.where(eh_prev, tabela["previsto"] * (1 - 1.96 * erro), np.nan)
    tabela["limite_superior"] = np.where(eh_prev, tabela["previsto"] * (1 + 1.96 * erro), np.nan)
    tabela["mes"] = tabela["mes"].dt.strftime("%Y-%m")
    return tabela, metricas, backtest


# --------------------------------------------------------------------------
# 4. Anomalias na receita diária
# --------------------------------------------------------------------------
def detectar_anomalias(pedidos: pd.DataFrame, limiar: float = 3.5) -> pd.DataFrame:
    """Compara cada dia com a mediana móvel de 29 dias; z-score robusto via MAD."""
    ent = pedidos[pedidos["status"] == "Entregue"]
    dia = ent.groupby("data_pedido").agg(receita=("receita_liquida", "sum"),
                                         evento=("evento_comercial", "first"))
    dia["referencia"] = dia["receita"].rolling(29, center=True, min_periods=10).median()
    resid = dia["receita"] - dia["referencia"]
    mad = (resid - resid.median()).abs().median()
    dia["z_robusto"] = 0.6745 * (resid - resid.median()) / mad
    dia["anomalia"] = dia["z_robusto"].abs() > limiar
    dia = dia.reset_index()
    dia["data_pedido"] = dia["data_pedido"].dt.strftime("%Y-%m-%d")
    return dia


# --------------------------------------------------------------------------
def main() -> dict:
    REPORTS.mkdir(exist_ok=True)
    with conectar() as con:
        pedidos = carregar_pedidos(con)
        vendas = carregar_vendas(con)

        anual = kpis_por_ano(pedidos)
        rfm, segmentos, aval_k, k, sil = segmentar_clientes(pedidos)
        previsao, metricas, backtest = prever_receita(pedidos)
        anomalias = detectar_anomalias(pedidos)

        rfm.to_sql("an_rfm_cliente", con, if_exists="replace", index=False)
        segmentos.to_sql("an_segmentos", con, if_exists="replace", index=False)
        aval_k.to_sql("an_escolha_k", con, if_exists="replace", index=False)
        previsao.to_sql("an_previsao_receita", con, if_exists="replace", index=False)
        metricas.to_sql("an_metricas_previsao", con, if_exists="replace", index=False)
        backtest.to_sql("an_backtest_previsao", con, if_exists="replace", index=False)
        anomalias.to_sql("an_receita_diaria", con, if_exists="replace", index=False)

    ent = vendas[vendas["status"] == "Entregue"]
    cat = ent.groupby("categoria").agg(receita=("receita_liquida", "sum"), margem=("margem_bruta", "sum"))
    cat["margem_pct"] = cat["margem"] / cat["receita"]
    bf = ent[ent["evento_comercial"] == "Black Friday"].groupby("categoria").agg(
        receita=("receita_liquida", "sum"), margem=("margem_bruta", "sum"))
    bf["margem_pct"] = bf["margem"] / bf["receita"]
    devol = (vendas[vendas["status"] != "Cancelado"].drop_duplicates(["id_pedido", "categoria"])
             .groupby("categoria")["status"].apply(lambda s: (s == "Devolvido").mean()))
    regiao = ent.pivot_table(index="regiao_cliente", columns="ano", values="receita_liquida", aggfunc="sum")
    regiao["crescimento_2023_2025"] = regiao[2025] / regiao[2023] - 1

    resultados = {
        "kpis_por_ano": json.loads(anual.to_json(orient="index")),
        "kmeans": {"k_escolhido": k, "silhouette": sil, "segmentos": segmentos.to_dict(orient="records")},
        "previsao": {"metricas_backtest": metricas.to_dict(orient="records"),
                     "proximos_6_meses": previsao[previsao["tipo"] == "previsão"][
                         ["mes", "previsto", "limite_inferior", "limite_superior"]].to_dict(orient="records")},
        "categorias": json.loads(cat.to_json(orient="index")),
        "black_friday_por_categoria": json.loads(bf.to_json(orient="index")),
        "devolucao_por_categoria": devol.to_dict(),
        "crescimento_por_regiao": regiao["crescimento_2023_2025"].to_dict(),
        "dias_anomalos": anomalias[anomalias["anomalia"]][["data_pedido", "receita", "evento", "z_robusto"]]
        .to_dict(orient="records"),
    }
    (REPORTS / "resultados_analise.json").write_text(
        json.dumps(resultados, indent=2, ensure_ascii=False, default=float), encoding="utf-8")
    return resultados


if __name__ == "__main__":
    r = main()
    print("KPIs por ano:\n", pd.DataFrame(r["kpis_por_ano"]).T.round(3).to_string())
    print(f"\nK-means: k={r['kmeans']['k_escolhido']} silhouette={r['kmeans']['silhouette']:.3f}")
    print(pd.DataFrame(r["kmeans"]["segmentos"]).round(2).to_string(index=False))
    print("\nPrevisão (backtest):\n", pd.DataFrame(r["previsao"]["metricas_backtest"]).round(4).to_string(index=False))
    print(f"\nDias anômalos: {len(r['dias_anomalos'])}")
