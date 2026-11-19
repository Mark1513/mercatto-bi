"""
Dashboard interativo — Mercatto (Streamlit + Plotly)

Executar a partir da raiz do projeto:
    streamlit run dashboard/app.py

Se a base ainda não existir (ex.: primeira execução no Streamlit Community Cloud),
o próprio dashboard roda o pipeline completo (gerar -> ETL -> validar -> analisar).
"""
import json
import sqlite3
import sys
import threading
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
DB = RAIZ / "data" / "processed" / "bi.db"
QUALIDADE = RAIZ / "reports" / "qualidade.json"

CORES = {"Online": "#2E6FBA", "Loja física": "#E08A2E"}
PALETA = ["#2E6FBA", "#E08A2E", "#3A9E6F", "#C24C4C", "#7A5CB8", "#8C7B3F"]
COR_SEG = {"Campeões": "#3A9E6F", "Regulares": "#2E6FBA", "Em risco": "#E08A2E", "Hibernando": "#9A9A9A",
           "Novos": "#7A5CB8"}
ACOES_SEG = {
    "Campeões": "Programa de fidelidade, acesso antecipado a lançamentos; evitar descontos desnecessários.",
    "Regulares": "Cross-sell por categoria e cashback para aumentar a frequência.",
    "Em risco": "Campanha de reativação personalizada (já foram bons clientes): cupom com prazo curto.",
    "Hibernando": "Comunicação de baixo custo (e-mail/CRM); não investir mídia paga.",
    "Novos": "Jornada de boas-vindas e incentivo à 2ª compra.",
}

st.set_page_config(page_title="Mercatto | Painel de BI", page_icon="📊", layout="wide")


# --------------------------------------------------------------------------
# Dados
# --------------------------------------------------------------------------
def base_pronta() -> bool:
    if not (DB.exists() and QUALIDADE.exists()):
        return False
    with sqlite3.connect(DB) as con:  # a análise grava as tabelas an_* por último
        return con.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'an_receita_diaria'").fetchone()[0] == 1


@st.cache_resource(show_spinner=False)
def _trava() -> threading.Lock:
    return threading.Lock()  # uma única trava por servidor


def garantir_base() -> bool:
    """Roda o pipeline se a base não existir (só uma sessão por vez; as outras esperam)."""
    if base_pronta():
        return True
    with _trava():
        if base_pronta():  # outra sessão já gerou enquanto esta esperava
            return True
        return _rodar_pipeline()


def _rodar_pipeline() -> bool:
    sys.path.insert(0, str(RAIZ))
    from src import analise, etl, gerar_base, validacao

    with st.status("Primeira execução: gerando a base de dados (≈ 1 minuto)…", expanded=True) as status:
        st.write("1/4 Gerando a base sintética (seed 42)…")
        gerar_base.main(seed=42)
        st.write("2/4 ETL: limpeza, padronização e carga no SQLite…")
        etl.main()
        st.write("3/4 Validando a qualidade (23 testes)…")
        if not validacao.main():
            status.update(label="A validação de qualidade falhou.", state="error")
            return False
        st.write("4/4 Calculando KPIs, segmentação RFM, previsão e anomalias…")
        analise.main()
        status.update(label="Base gerada com sucesso.", state="complete", expanded=False)
    return True


@st.cache_data
def carregar():
    if not base_pronta():
        return None
    with sqlite3.connect(DB) as con:
        vendas = pd.read_sql("SELECT * FROM vw_vendas", con, parse_dates=["data_pedido"])
        pedidos = pd.read_sql("SELECT p.*, c.regiao AS regiao_cliente FROM fato_pedido p "
                              "JOIN dim_cliente c USING(id_cliente)", con, parse_dates=["data_pedido"])
        rfm = pd.read_sql("SELECT * FROM an_rfm_cliente", con)
        segmentos = pd.read_sql("SELECT * FROM an_segmentos", con)
        escolha_k = pd.read_sql("SELECT * FROM an_escolha_k", con)
        previsao = pd.read_sql("SELECT * FROM an_previsao_receita", con)
        metricas = pd.read_sql("SELECT * FROM an_metricas_previsao", con)
        diaria = pd.read_sql("SELECT * FROM an_receita_diaria", con, parse_dates=["data_pedido"])
        lojas = pd.read_sql("SELECT * FROM dim_loja", con)
    vendas = vendas.merge(rfm[["id_cliente", "segmento"]], on="id_cliente", how="left")
    vendas["segmento"] = vendas["segmento"].fillna("Sem compra entregue")
    qualidade = json.loads(QUALIDADE.read_text(encoding="utf-8")) if QUALIDADE.exists() else None
    return dict(vendas=vendas, pedidos=pedidos, rfm=rfm, segmentos=segmentos, escolha_k=escolha_k,
                previsao=previsao, metricas=metricas, diaria=diaria, lojas=lojas, qualidade=qualidade)


def brl(v: float, curto: bool = True) -> str:
    if pd.isna(v):
        return "—"
    if curto and abs(v) >= 1e6:
        return f"R$ {v / 1e6:,.2f} mi".replace(",", "X").replace(".", ",").replace("X", ".")
    if curto and abs(v) >= 1e3:
        return f"R$ {v / 1e3:,.1f} mil".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(v: float, casas: int = 1) -> str:
    return "—" if pd.isna(v) else f"{v * 100:.{casas}f}%".replace(".", ",")


def kpis(itens: pd.DataFrame) -> dict:
    """KPIs calculados no nível do item (respeitam qualquer filtro, inclusive categoria)."""
    ent = itens[itens["status"] == "Entregue"]
    fat = itens[itens["status"].isin(["Entregue", "Devolvido"])]
    receita = ent["receita_liquida"].sum()
    n_ped = ent["id_pedido"].nunique()
    ped_fat = fat.drop_duplicates("id_pedido")
    return {
        "receita": receita,
        "margem_pct": ent["margem_bruta"].sum() / receita if receita else np.nan,
        "ticket": receita / n_ped if n_ped else np.nan,
        "pedidos": n_ped,
        "devolucao": (ped_fat["status"] == "Devolvido").mean() if len(ped_fat) else np.nan,
        "clientes": ent["id_cliente"].nunique(),
        "desconto": ent["valor_desconto"].sum() / ent["receita_bruta"].sum() if len(ent) else np.nan,
    }


def layout(fig, altura=360, legenda=True, datas=False):
    if datas:  # eixo de datas no formato brasileiro (o Plotly usa nomes de meses em inglês)
        fig.update_xaxes(tickformat="%m/%Y", hoverformat="%d/%m/%Y")
    fig.update_layout(height=altura, margin=dict(l=10, r=10, t=70, b=10), showlegend=legenda,
                      title_y=0.97, legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
                      separators=",.",
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.2)")
    return fig


def plot(fig, **kw):
    st.plotly_chart(layout(fig, **kw), width="stretch", config={"displaylogo": False})


# --------------------------------------------------------------------------
if not garantir_base():
    st.error("Não foi possível gerar a base. Rode `python run_all.py` e veja reports/relatorio_qualidade.md.")
    st.stop()
dados = carregar()
if dados is None:
    st.error("Base não encontrada. Rode `python run_all.py` na raiz do projeto antes de abrir o dashboard.")
    st.stop()

vendas = dados["vendas"]

# ----------------------------- Filtros -----------------------------------
st.sidebar.title("📊 Mercatto")
st.sidebar.caption("Varejo omnicanal fictício · dados sintéticos")
dmin, dmax = vendas["data_pedido"].min().date(), vendas["data_pedido"].max().date()
periodo = st.sidebar.date_input("Período", (pd.Timestamp("2025-01-01").date(), dmax), min_value=dmin,
                                max_value=dmax, format="DD/MM/YYYY")
if not isinstance(periodo, (tuple, list)) or len(periodo) != 2:
    st.sidebar.info("Selecione a data inicial e a final.")
    st.stop()
ini, fim = pd.Timestamp(periodo[0]), pd.Timestamp(periodo[1])

def multi(rotulo, coluna):
    opcoes = sorted(vendas[coluna].dropna().unique())
    return st.sidebar.multiselect(rotulo, opcoes, placeholder="Todos")

f_canal = multi("Canal", "canal")
f_regiao = multi("Região do cliente", "regiao_cliente")
f_categoria = multi("Categoria", "categoria")
f_segmento = multi("Segmento RFM", "segmento")
st.sidebar.divider()
st.sidebar.caption("Receita e margem consideram apenas pedidos **entregues**. "
                   "A comparação (Δ) é contra o período imediatamente anterior, de mesma duração.")


def aplicar(df, inicio, final):
    m = df["data_pedido"].between(inicio, final)
    for col, val in (("canal", f_canal), ("regiao_cliente", f_regiao), ("categoria", f_categoria),
                     ("segmento", f_segmento)):
        if val:
            m &= df[col].isin(val)
    return df[m]


filtrado = aplicar(vendas, ini, fim)
duracao = fim - ini
anterior = aplicar(vendas, ini - duracao - pd.Timedelta(days=1), ini - pd.Timedelta(days=1))
k_atual, k_ant = kpis(filtrado), kpis(anterior)

# ----------------------------- Cabeçalho ---------------------------------
st.title("Painel de desempenho comercial")
st.caption(f"Período: {ini:%d/%m/%Y} a {fim:%d/%m/%Y} · {len(filtrado):,} itens vendidos no filtro".replace(",", "."))

if filtrado.empty:
    st.warning("Nenhum dado para os filtros selecionados.")
    st.stop()


def delta(chave, tipo="pct"):
    a, b = k_atual[chave], k_ant[chave]
    if pd.isna(a) or pd.isna(b) or b == 0:
        return None
    if tipo == "pp":
        return f"{(a - b) * 100:+.1f}".replace(".", ",") + " p.p."
    return f"{(a / b - 1) * 100:+.1f}%".replace(".", ",")


# Duas linhas de 3 cartões: os valores não ficam cortados em telas estreitas
c = st.columns(3) + st.columns(3)
receita_mi = f"{k_atual['receita'] / 1e6:.1f} mi".replace(".", ",")
c[0].metric("Receita (R$)", receita_mi, delta("receita"), border=True,
            help=brl(k_atual["receita"], curto=False))
c[1].metric("Margem bruta", pct(k_atual["margem_pct"]), delta("margem_pct", "pp"), border=True)
c[2].metric("Ticket médio (R$)", f"{k_atual['ticket']:,.0f}".replace(",", "."), delta("ticket"), border=True)
c[3].metric("Pedidos entregues", f"{k_atual['pedidos']:,}".replace(",", "."), delta("pedidos"), border=True)
c[4].metric("Taxa de devolução", pct(k_atual["devolucao"]), delta("devolucao", "pp"), delta_color="inverse",
            border=True)
c[5].metric("Clientes ativos", f"{k_atual['clientes']:,}".replace(",", "."), delta("clientes"), border=True)

aba = st.tabs(["Visão geral", "Produtos e margem", "Clientes (RFM)", "Previsão e anomalias",
               "Regiões e lojas", "Qualidade e governança"])
ent = filtrado[filtrado["status"] == "Entregue"]

# ----------------------------- 1. Visão geral ----------------------------
with aba[0]:
    col1, col2 = st.columns([2, 1])
    with col1:
        mensal = (ent.groupby([pd.Grouper(key="data_pedido", freq="MS"), "canal"])["receita_liquida"]
                  .sum().reset_index())
        fig = px.area(mensal, x="data_pedido", y="receita_liquida", color="canal", color_discrete_map=CORES,
                      title="Receita líquida mensal por canal",
                      labels={"data_pedido": "", "receita_liquida": "Receita (R$)", "canal": ""})
        plot(fig, datas=True)
    with col2:
        canal = ent.groupby("canal")["receita_liquida"].sum().reset_index()
        canal["part"] = canal["receita_liquida"] / canal["receita_liquida"].sum()
        fig = px.bar(canal, x="canal", y="part", color="canal", color_discrete_map=CORES, text_auto=".1%",
                     title="Participação na receita", labels={"part": "", "canal": ""})
        fig.update_yaxes(tickformat=".0%")
        plot(fig, legenda=False)

    col1, col2 = st.columns(2)
    with col1:
        cat = (ent.groupby("categoria")["receita_liquida"].sum().sort_values().reset_index())
        fig = px.bar(cat, x="receita_liquida", y="categoria", orientation="h", title="Receita por categoria",
                     labels={"receita_liquida": "Receita (R$)", "categoria": ""}, color_discrete_sequence=PALETA)
        plot(fig, legenda=False)
    with col2:
        top = (ent.groupby(["nome_produto", "categoria"])
               .agg(receita=("receita_liquida", "sum"), unidades=("quantidade", "sum"),
                    margem=("margem_bruta", "sum"))
               .sort_values("receita", ascending=False).head(10).reset_index())
        top["margem_%"] = top["margem"] / top["receita"]
        st.markdown("**Top 10 produtos por receita**")
        st.dataframe(top[["nome_produto", "categoria", "receita", "unidades", "margem_%"]], hide_index=True,
                     width="stretch", column_config={
                         "nome_produto": "Produto", "categoria": "Categoria",
                         "receita": st.column_config.NumberColumn("Receita", format="R$ %.0f"),
                         "unidades": "Unid.",
                         "margem_%": st.column_config.ProgressColumn("Margem", format="percent", min_value=-0.2,
                                                                     max_value=0.7)})

# ----------------------------- 2. Produtos e margem ----------------------
with aba[1]:
    cat = ent.groupby("categoria").agg(receita=("receita_liquida", "sum"), margem=("margem_bruta", "sum"),
                                       desconto=("valor_desconto", "sum"), bruta=("receita_bruta", "sum"))
    cat["margem_%"] = cat["margem"] / cat["receita"]
    cat["desconto_%"] = cat["desconto"] / cat["bruta"]
    cat = cat.sort_values("receita", ascending=False).reset_index()
    col1, col2 = st.columns(2)
    with col1:
        fig = px.scatter(cat, x="desconto_%", y="margem_%", size="receita", color="categoria", text="categoria",
                         color_discrete_sequence=PALETA, size_max=55,
                         title="Desconto médio × margem (tamanho = receita)",
                         labels={"desconto_%": "Desconto médio", "margem_%": "Margem bruta"})
        fig.update_traces(textposition="top center")
        fig.update_xaxes(tickformat=".0%")
        fig.update_yaxes(tickformat=".0%")
        plot(fig, legenda=False)
    with col2:
        bf = ent.assign(periodo=np.where(ent["evento_comercial"] == "Black Friday", "Black Friday", "Resto do período"))
        m = bf.groupby(["categoria", "periodo"]).agg(r=("receita_liquida", "sum"), m=("margem_bruta", "sum"))
        m = (m["m"] / m["r"]).rename("margem").reset_index()
        fig = px.bar(m, x="margem", y="categoria", color="periodo", barmode="group", orientation="h",
                     title="Margem bruta: Black Friday × resto do período",
                     color_discrete_map={"Black Friday": "#C24C4C", "Resto do período": "#2E6FBA"},
                     labels={"margem": "Margem bruta", "categoria": "", "periodo": ""})
        fig.update_xaxes(tickformat=".0%")
        fig.add_vline(x=0, line_color="gray")
        plot(fig)

    faixas = pd.cut(ent["desconto_pct"], [-.01, 0, .10, .20, .30, .5],
                    labels=["0%", "1–10%", "11–20%", "21–30%", ">30%"])
    heat = ent.assign(faixa=faixas).groupby(["categoria", "faixa"], observed=True).agg(
        r=("receita_liquida", "sum"), m=("margem_bruta", "sum"))
    heat = (heat["m"] / heat["r"]).unstack()
    fig = px.imshow(heat, text_auto=".0%", color_continuous_scale="RdYlGn", color_continuous_midpoint=0,
                    aspect="auto", title="Margem bruta por categoria e faixa de desconto",
                    labels=dict(x="Faixa de desconto", y="", color="Margem"))
    fig.update_coloraxes(colorbar_tickformat=".0%")
    plot(fig, altura=330)

    neg = ent[ent["margem_bruta"] < 0]
    if len(neg):
        n_neg = f"{len(neg):,}".replace(",", ".")
        st.warning(f"**{n_neg} itens vendidos abaixo do custo** no filtro atual, prejuízo bruto de "
                   f"**{brl(-neg['margem_bruta'].sum())}**. {neg['evento_comercial'].eq('Black Friday').mean():.0%} "
                   "deles ocorreram na Black Friday.")

    base = filtrado[filtrado["status"] != "Cancelado"].drop_duplicates(["id_pedido", "categoria"])
    dev = (base.groupby(["categoria", "canal"])["status"].apply(lambda s: (s == "Devolvido").mean())
           .rename("taxa").reset_index())
    fig = px.bar(dev, x="categoria", y="taxa", color="canal", barmode="group", color_discrete_map=CORES,
                 title="Taxa de devolução por categoria e canal", text_auto=".1%",
                 labels={"taxa": "Pedidos devolvidos", "categoria": "", "canal": ""})
    fig.update_yaxes(tickformat=".0%")
    plot(fig)

# ----------------------------- 3. Clientes (RFM) -------------------------
with aba[2]:
    st.caption("Segmentação calculada sobre toda a base (até 31/12/2025) com K-means sobre Recência, "
               "Frequência e Valor. Os filtros de canal/região/categoria não alteram os segmentos.")
    seg = dados["segmentos"].copy()
    col1, col2 = st.columns([3, 2])
    with col1:
        long = seg.melt(id_vars="segmento", value_vars=["pct_clientes", "pct_receita"], var_name="medida",
                        value_name="valor")
        long["medida"] = long["medida"].map({"pct_clientes": "% dos clientes", "pct_receita": "% da receita"})
        fig = px.bar(long, x="segmento", y="valor", color="medida", barmode="group", text_auto=".0%",
                     title="Peso de cada segmento: clientes × receita",
                     color_discrete_sequence=["#9A9A9A", "#2E6FBA"], labels={"valor": "", "segmento": "",
                                                                            "medida": ""})
        fig.update_yaxes(tickformat=".0%")
        plot(fig)
    with col2:
        amostra = dados["rfm"].sample(min(3000, len(dados["rfm"])), random_state=1)
        fig = px.scatter(amostra, x="recencia_dias", y="monetario", color="segmento", log_y=True, opacity=.6,
                         color_discrete_map=COR_SEG, title="Recência × valor (amostra de clientes)",
                         labels={"recencia_dias": "Dias desde a última compra", "monetario": "Receita (R$)",
                                 "segmento": ""})
        fig.update_traces(marker_size=5)
        plot(fig)
    seg["acao_sugerida"] = seg["segmento"].map(ACOES_SEG)
    st.dataframe(seg[["segmento", "clientes", "recencia_media", "frequencia_media", "monetario_medio",
                      "pct_receita", "acao_sugerida"]], hide_index=True, width="stretch", column_config={
        "segmento": "Segmento", "clientes": "Clientes",
        "recencia_media": st.column_config.NumberColumn("Recência média (dias)", format="%.0f"),
        "frequencia_media": st.column_config.NumberColumn("Pedidos/cliente", format="%.1f"),
        "monetario_medio": st.column_config.NumberColumn("Receita/cliente", format="R$ %.0f"),
        "pct_receita": st.column_config.NumberColumn("% da receita", format="percent"),
        "acao_sugerida": st.column_config.TextColumn("Ação sugerida", width="large")})
    with st.expander("Como o número de segmentos foi escolhido"):
        k = dados["escolha_k"]
        col1, col2 = st.columns(2)
        with col1:
            plot(px.line(k, x="k", y="inercia", markers=True, title="Método do cotovelo"), altura=280)
        with col2:
            plot(px.line(k, x="k", y="silhouette", markers=True, title="Coeficiente de silhouette"), altura=280)
        st.markdown("k = 2 tem o maior silhouette, mas separa só 'bons' e 'ruins', o que não ajuda a decidir "
                    "ações. Entre 3 e 6 grupos, **k = 4** tem o melhor silhouette (≈ 0,34, separação moderada).")

# ----------------------------- 4. Previsão e anomalias -------------------
with aba[3]:
    p = dados["previsao"].copy()
    p["mes"] = pd.to_datetime(p["mes"])
    hist, tst, fut = (p[p["tipo"] == t] for t in ("histórico", "teste (fora da amostra)", "previsão"))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=fut["mes"].tolist() + fut["mes"].tolist()[::-1],
                             y=fut["limite_superior"].tolist() + fut["limite_inferior"].tolist()[::-1],
                             fill="toself", fillcolor="rgba(194,76,76,0.15)", line=dict(width=0),
                             name="Faixa ~95%", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=hist["mes"], y=hist["real"], name="Real", line=dict(color="#2E6FBA")))
    fig.add_trace(go.Scatter(x=tst["mes"], y=tst["previsto"], name="Previsto (teste fora da amostra)",
                             line=dict(color="#E08A2E", dash="dash")))
    fig.add_trace(go.Scatter(x=fut["mes"], y=fut["previsto"], name="Previsão", line=dict(color="#C24C4C")))
    fig.update_layout(title="Receita líquida mensal: histórico e previsão (base completa)")
    plot(fig, altura=400, datas=True)

    met = dados["metricas"].copy()
    col1, col2 = st.columns([3, 2])
    with col1:
        st.markdown("**Comparação de modelos (validação com origem móvel, 10 janelas de 3 meses)**")
        st.dataframe(met[["modelo", "MAPE", "MAE", "escolhido"]], hide_index=True, width="stretch",
                     column_config={"modelo": "Modelo",
                                    "MAPE": st.column_config.NumberColumn("MAPE médio", format="percent"),
                                    "MAE": st.column_config.NumberColumn("Erro médio (R$)", format="R$ %.0f"),
                                    "escolhido": "Escolhido"})
    with col2:
        prox = fut[["mes", "previsto", "limite_inferior", "limite_superior"]].copy()
        prox["mes"] = prox["mes"].dt.strftime("%m/%Y")
        st.markdown("**Próximos meses**")
        st.dataframe(prox, hide_index=True, width="stretch", column_config={
            "mes": "Mês", "previsto": st.column_config.NumberColumn("Previsto", format="R$ %.0f"),
            "limite_inferior": st.column_config.NumberColumn("Mín.", format="R$ %.0f"),
            "limite_superior": st.column_config.NumberColumn("Máx.", format="R$ %.0f")})

    d = dados["diaria"]
    d = d[d["data_pedido"].between(ini, fim)]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d["data_pedido"], y=d["receita"], name="Receita diária",
                             line=dict(color="#2E6FBA", width=1)))
    fig.add_trace(go.Scatter(x=d["data_pedido"], y=d["referencia"], name="Mediana móvel 29 dias",
                             line=dict(color="gray")))
    an = d[d["anomalia"] == 1]
    fig.add_trace(go.Scatter(x=an["data_pedido"], y=an["receita"], mode="markers", name="Anomalia",
                             marker=dict(color="#C24C4C", size=9), text=an["evento"],
                             hovertemplate="%{x|%d/%m/%Y}<br>R$ %{y:,.0f}<br>%{text}<extra></extra>"))
    fig.update_layout(title="Receita diária e dias anômalos (|z robusto| > 3,5) no período selecionado")
    plot(fig, altura=360, datas=True)

# ----------------------------- 5. Regiões e lojas ------------------------
with aba[4]:
    col1, col2 = st.columns(2)
    with col1:
        reg = ent.groupby("regiao_cliente").agg(receita=("receita_liquida", "sum"),
                                                clientes=("id_cliente", "nunique")).reset_index()
        reg["receita_por_cliente"] = reg["receita"] / reg["clientes"]
        fig = px.bar(reg.sort_values("receita"), x="receita", y="regiao_cliente", orientation="h",
                     title="Receita por região do cliente", color_discrete_sequence=PALETA,
                     labels={"receita": "Receita (R$)", "regiao_cliente": ""})
        plot(fig, legenda=False)
    with col2:
        ano_reg = (vendas[vendas["status"] == "Entregue"]
                   .groupby(["ano", "regiao_cliente"])["receita_liquida"].sum().reset_index())
        base23 = ano_reg[ano_reg["ano"] == ano_reg["ano"].min()].set_index("regiao_cliente")["receita_liquida"]
        ano_reg["indice"] = ano_reg["receita_liquida"] / ano_reg["regiao_cliente"].map(base23) * 100
        fig = px.line(ano_reg, x="ano", y="indice", color="regiao_cliente", markers=True,
                      color_discrete_sequence=PALETA, title="Crescimento por região (2023 = 100, base completa)",
                      labels={"indice": "Índice", "ano": "", "regiao_cliente": ""})
        fig.update_xaxes(dtick=1)
        plot(fig)
    fis = ent[ent["canal"] == "Loja física"]
    if len(fis):
        lj = (fis.groupby([pd.Grouper(key="data_pedido", freq="QS"), "nome_loja"])["receita_liquida"].sum()
              .reset_index())
        fig = px.line(lj, x="data_pedido", y="receita_liquida", color="nome_loja", markers=True,
                      title="Receita trimestral por loja física",
                      labels={"data_pedido": "", "receita_liquida": "Receita (R$)", "nome_loja": ""})
        plot(fig, altura=380, datas=True)
        st.caption("A loja de Recife foi inaugurada em 15/03/2024.")

# ----------------------------- 6. Qualidade e governança -----------------
with aba[5]:
    q = dados["qualidade"]
    if q:
        testes = pd.DataFrame(q["testes"])
        ok = (testes["problemas"] == 0).sum()
        c = st.columns(3)
        c[0].metric("Testes de qualidade aprovados", f"{ok}/{len(testes)}", border=True)
        c[1].metric("Problemas inseridos e tratados", f"{sum(q['problemas_inseridos'].values()):,}".replace(",", "."),
                    border=True)
        c[2].metric("Linhas na fato de itens", f"{q['volumes']['fato_item_pedido']:,}".replace(",", "."), border=True)
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Testes na base tratada**")
            testes["resultado"] = np.where(testes["problemas"] == 0, "✅ OK", "❌ Falhou")
            st.dataframe(testes[["dimensao", "teste", "problemas", "resultado"]], hide_index=True,
                         width="stretch", height=420)
        with col2:
            st.markdown("**Problemas encontrados na base bruta**")
            pi = pd.Series(q["problemas_inseridos"]).rename("ocorrências").reset_index()
            pi["index"] = pi["index"].str.replace("_", " ")
            st.dataframe(pi.rename(columns={"index": "problema"}), hide_index=True, width="stretch", height=420)
    st.markdown("""
**Privacidade e uso responsável (LGPD)**
- Dados **100% sintéticos**: nenhuma pessoa real é representada. Nomes e e-mails da base bruta são fictícios
  (domínio `email.exemplo`).
- **Minimização:** nome, e-mail e data de nascimento exata **não** chegam à camada analítica. O painel usa só o ID
  do cliente e a faixa etária.
- O painel mostra apenas dados **agregados**; não há busca por cliente individual.
- Em produção: acesso por perfil (ex.: gerente regional vê só sua região), banco fora de pastas públicas e
  registro de quem acessa.
""")
