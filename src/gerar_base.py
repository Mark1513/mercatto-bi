"""
Gerador da base de dados sintética — Mercatto (varejo omnicanal FICTÍCIO).

Gera 5 tabelas relacionadas em CSV, na pasta data/raw:
    clientes.csv, produtos.csv, lojas.csv, pedidos.csv, itens_pedido.csv

Os dados "brutos" recebem, de propósito, problemas de qualidade típicos de
sistemas reais (duplicidades, nulos, formatos misturados, chaves órfãs etc.),
que serão tratados no ETL (src/etl.py). O que foi inserido fica registrado em
data/raw/_problemas_inseridos.json para conferência.

Padrões de negócio simulados (para que a análise tenha o que descobrir):
    * sazonalidade (Dia das Mães, Dia dos Pais, Black Friday e Natal);
    * crescimento do canal online e da região Nordeste;
    * abertura da loja de Recife em 15/03/2024;
    * perfis ocultos de clientes (fiel, regular, ocasional, promocional) e churn;
    * descontos agressivos na Black Friday corroendo a margem de Eletrônicos;
    * taxa de devolução maior em Moda.

Execução (a partir da raiz do projeto):
    python -m src.gerar_base --seed 42 --clientes 8000
"""
from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

RAIZ = Path(__file__).resolve().parents[1]
DATA_INICIO = pd.Timestamp("2023-01-01")
DATA_FIM = pd.Timestamp("2025-12-31")

# --------------------------------------------------------------------------
# Parâmetros do cenário
# --------------------------------------------------------------------------
REGIOES = ["Sudeste", "Nordeste", "Sul", "Centro-Oeste", "Norte"]
PESO_REGIAO_BASE = np.array([0.45, 0.20, 0.16, 0.09, 0.10])

UFS = {  # UF: (região, peso dentro da região, cidades)
    "SP": ("Sudeste", 0.50, ["São Paulo", "Campinas", "Santos"]),
    "RJ": ("Sudeste", 0.25, ["Rio de Janeiro", "Niterói"]),
    "MG": ("Sudeste", 0.20, ["Belo Horizonte", "Uberlândia"]),
    "ES": ("Sudeste", 0.05, ["Vitória"]),
    "BA": ("Nordeste", 0.30, ["Salvador", "Feira de Santana"]),
    "PE": ("Nordeste", 0.30, ["Recife", "Olinda"]),
    "CE": ("Nordeste", 0.20, ["Fortaleza"]),
    "MA": ("Nordeste", 0.10, ["São Luís"]),
    "RN": ("Nordeste", 0.10, ["Natal"]),
    "PR": ("Sul", 0.40, ["Curitiba", "Londrina"]),
    "RS": ("Sul", 0.40, ["Porto Alegre", "Caxias do Sul"]),
    "SC": ("Sul", 0.20, ["Florianópolis", "Joinville"]),
    "DF": ("Centro-Oeste", 0.45, ["Brasília"]),
    "GO": ("Centro-Oeste", 0.40, ["Goiânia"]),
    "MT": ("Centro-Oeste", 0.15, ["Cuiabá"]),
    "PA": ("Norte", 0.45, ["Belém"]),
    "AM": ("Norte", 0.40, ["Manaus"]),
    "TO": ("Norte", 0.15, ["Palmas"]),
}

LOJAS = [  # id, nome, tipo, cidade, uf, região, data de abertura
    (1, "Mercatto Paulista", "Física", "São Paulo", "SP", "Sudeste", "2018-03-10"),
    (2, "Mercatto Campinas", "Física", "Campinas", "SP", "Sudeste", "2019-08-01"),
    (3, "Mercatto Barra", "Física", "Rio de Janeiro", "RJ", "Sudeste", "2019-05-20"),
    (4, "Mercatto Savassi", "Física", "Belo Horizonte", "MG", "Sudeste", "2020-02-14"),
    (5, "Mercatto Curitiba", "Física", "Curitiba", "PR", "Sul", "2019-11-05"),
    (6, "Mercatto Porto Alegre", "Física", "Porto Alegre", "RS", "Sul", "2021-04-12"),
    (7, "Mercatto Salvador", "Física", "Salvador", "BA", "Nordeste", "2021-09-01"),
    (8, "Mercatto Recife", "Física", "Recife", "PE", "Nordeste", "2024-03-15"),
    (9, "Mercatto Brasília", "Física", "Brasília", "DF", "Centro-Oeste", "2020-06-30"),
    (10, "Mercatto Belém", "Física", "Belém", "PA", "Norte", "2022-10-10"),
    (11, "Mercatto Online", "Online", "São Paulo", "SP", "Nacional", "2017-01-01"),
]
ID_LOJA_ONLINE = 11

# categoria: itens (nome, preço base), faixa de margem, popularidade, prob. devolução
CATEGORIAS = {
    "Eletrônicos": dict(
        itens=[("Smartphone 128GB", 1899), ("Smart TV 50\"", 2799), ("Fone Bluetooth", 199),
               ("Caixa de Som Portátil", 349), ("Smartwatch", 899), ("Tablet 10\"", 1499),
               ("Câmera de Ação", 1199), ("Console de Videogame", 3999), ("Soundbar", 999),
               ("Carregador Turbo", 89)],
        margem=(0.10, 0.20), pop=0.22, devol=0.04),
    "Informática": dict(
        itens=[("Notebook 15\"", 3899), ("Monitor 24\"", 899), ("Mouse sem Fio", 79),
               ("Teclado Mecânico", 299), ("SSD 1TB", 459), ("Roteador Wi-Fi 6", 399),
               ("Webcam Full HD", 249), ("Impressora Multifuncional", 1099),
               ("Headset Gamer", 329), ("HD Externo 2TB", 549)],
        margem=(0.15, 0.25), pop=0.14, devol=0.04),
    "Casa e Cozinha": dict(
        itens=[("Air Fryer 4L", 449), ("Liquidificador", 199), ("Cafeteira Expresso", 699),
               ("Jogo de Panelas", 379), ("Aspirador Robô", 1499), ("Micro-ondas 30L", 799),
               ("Ventilador de Coluna", 229), ("Jogo de Toalhas", 129),
               ("Panela de Pressão", 159), ("Purificador de Água", 649)],
        margem=(0.28, 0.40), pop=0.20, devol=0.03),
    "Moda": dict(
        itens=[("Tênis Casual", 299), ("Jaqueta Jeans", 259), ("Camiseta Básica", 59),
               ("Calça Jeans", 189), ("Vestido Midi", 219), ("Mochila", 179),
               ("Óculos de Sol", 249), ("Bolsa Transversal", 199), ("Moletom", 169),
               ("Sandália", 99)],
        margem=(0.45, 0.60), pop=0.18, devol=0.13),
    "Esporte e Lazer": dict(
        itens=[("Bicicleta Aro 29", 2199), ("Tênis de Corrida", 399), ("Kit Halteres", 249),
               ("Tapete de Yoga", 89), ("Barraca 4 Pessoas", 599), ("Garrafa Térmica", 79),
               ("Bola de Futebol", 119), ("Esteira Elétrica", 3299), ("Patinete", 449),
               ("Cooler 30L", 299)],
        margem=(0.30, 0.45), pop=0.12, devol=0.04),
    "Beleza e Saúde": dict(
        itens=[("Secador de Cabelo", 249), ("Prancha Alisadora", 199), ("Perfume 100ml", 329),
               ("Kit Skincare", 159), ("Barbeador Elétrico", 279),
               ("Escova Dental Elétrica", 229), ("Hidratante Corporal", 49),
               ("Balança Digital", 119), ("Massageador", 189), ("Protetor Solar", 69)],
        margem=(0.40, 0.55), pop=0.14, devol=0.03),
}
MARCAS = ["Voltex", "Nordika", "Aurora", "Kamba", "Lumen", "Trivo", "Zênite", "Orbe"]

# Perfis ocultos de cliente (não vão para os CSV — a análise precisa descobri-los)
SEGMENTOS = ["fiel", "regular", "ocasional", "promocional"]
PROB_SEGMENTO = [0.15, 0.35, 0.30, 0.20]
PEDIDOS_ANO = {"fiel": 9.0, "regular": 3.5, "ocasional": 1.2, "promocional": 2.0}
PROB_CHURN = {"fiel": 0.05, "regular": 0.25, "ocasional": 0.40, "promocional": 0.35}

FATOR_MES = np.array([0.85, 0.80, 0.90, 0.90, 1.05, 0.95, 0.95, 1.00, 0.95, 1.00, 1.50, 1.60])


# --------------------------------------------------------------------------
# Funções auxiliares
# --------------------------------------------------------------------------
def sem_acento(txt: str) -> str:
    return unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode("ascii")


def escolha_por_linha(rng: np.random.Generator, probs: np.ndarray) -> np.ndarray:
    """Sorteia um índice por linha, cada linha com seu próprio vetor de probabilidades."""
    acumulada = probs.cumsum(axis=1)
    acumulada /= acumulada[:, -1:]
    u = rng.random(len(probs))[:, None]
    return (acumulada < u).sum(axis=1)


def janelas_black_friday(dias: pd.DatetimeIndex) -> np.ndarray:
    """Black Friday = sexta-feira após a 4ª quinta de novembro; janela de sexta a segunda (Cyber Monday)."""
    marca = np.zeros(len(dias), dtype=bool)
    for ano in sorted(set(dias.year)):
        bf = data_black_friday(ano)
        marca |= (dias >= bf) & (dias <= bf + pd.Timedelta(days=3))
    return marca


def data_black_friday(ano: int) -> pd.Timestamp:
    nov1 = pd.Timestamp(year=ano, month=11, day=1)
    primeira_quinta = nov1 + pd.Timedelta(days=(3 - nov1.day_of_week) % 7)
    return primeira_quinta + pd.Timedelta(days=22)


# --------------------------------------------------------------------------
# Tabelas de dimensão
# --------------------------------------------------------------------------
def gerar_lojas() -> pd.DataFrame:
    return pd.DataFrame(LOJAS, columns=["id_loja", "nome_loja", "tipo_loja", "cidade",
                                        "uf", "regiao", "data_abertura"])


def gerar_produtos(rng: np.random.Generator) -> pd.DataFrame:
    linhas = []
    pid = 1
    for categoria, cfg in CATEGORIAS.items():
        for nome, preco_base in cfg["itens"]:
            for linha, mult_preco, ajuste_margem in (("Essencial", 1.0, 0.0), ("Premium", 1.6, 0.05)):
                preco = preco_base * mult_preco * rng.uniform(0.9, 1.1)
                preco = round(np.floor(preco) + 0.90, 2)  # preços terminados em ,90
                margem = rng.uniform(*cfg["margem"]) + ajuste_margem
                linhas.append({
                    "id_produto": pid,
                    "nome_produto": f"{nome} {linha}",
                    "categoria": categoria,
                    "marca": rng.choice(MARCAS),
                    "linha": linha,
                    "preco_lista": preco,
                    "custo_unitario": round(preco * (1 - margem), 2),
                })
                pid += 1
    return pd.DataFrame(linhas)


def gerar_clientes(n: int, rng: np.random.Generator, fake: Faker) -> pd.DataFrame:
    dias_periodo = (DATA_FIM - DATA_INICIO).days

    # Cadastro: 35% já eram clientes antes de 2023; o restante entra com captação crescente
    n_antigos = int(n * 0.35)
    antigos = DATA_INICIO - pd.to_timedelta(rng.integers(1, 4 * 365, n_antigos), unit="D")
    novos = DATA_INICIO + pd.to_timedelta(
        (rng.beta(1.4, 1.0, n - n_antigos) * dias_periodo).astype(int), unit="D")
    cadastro = pd.DatetimeIndex(np.concatenate([antigos.values, novos.values]))

    # Região: participação do Nordeste cresce ao longo do tempo (expansão da marca)
    frac = np.clip((cadastro - DATA_INICIO).days / dias_periodo, 0, 1)
    peso_ne = 0.20 + 0.16 * frac
    outros = np.delete(PESO_REGIAO_BASE, 1)
    outros = outros / outros.sum()
    probs = np.column_stack([outros[0] * (1 - peso_ne), peso_ne, outros[1] * (1 - peso_ne),
                             outros[2] * (1 - peso_ne), outros[3] * (1 - peso_ne)])
    regiao = np.array(REGIOES)[escolha_por_linha(rng, probs)]

    ufs, cidades = [], []
    for r in regiao:
        opcoes = [(uf, p) for uf, (reg, p, _) in UFS.items() if reg == r]
        pesos = np.array([p for _, p in opcoes])
        uf = opcoes[rng.choice(len(opcoes), p=pesos / pesos.sum())][0]
        ufs.append(uf)
        cidades.append(rng.choice(UFS[uf][2]))

    idade = np.clip(rng.normal(37, 12, n), 18, 80)
    nascimento = pd.Timestamp("2025-12-31") - pd.to_timedelta((idade * 365.25).astype(int), unit="D")

    nomes = [fake.name() for _ in range(n)]
    emails = []
    for i, nome in enumerate(nomes):
        partes = sem_acento(nome).lower().replace(".", "").split()
        emails.append(f"{partes[0]}.{partes[-1]}{i + 1}@email.exemplo")

    segmento = rng.choice(SEGMENTOS, size=n, p=PROB_SEGMENTO)
    canal_aquisicao = rng.choice(["Orgânico", "Redes Sociais", "Google Ads", "Indicação", "Loja Física"],
                                 size=n, p=[0.25, 0.25, 0.20, 0.10, 0.20])

    clientes = pd.DataFrame({
        "id_cliente": np.arange(1, n + 1),
        "nome": nomes,
        "email": emails,
        "data_nascimento": nascimento.strftime("%Y-%m-%d"),
        "cidade": cidades,
        "uf": ufs,
        "data_cadastro": cadastro.strftime("%Y-%m-%d"),
        "canal_aquisicao": canal_aquisicao,
    })
    # Atributos ocultos, usados só para simular o comportamento de compra
    ocultos = pd.DataFrame({
        "segmento": segmento,
        "idade": idade,
        "regiao": regiao,
        "pref_online": rng.normal(0, 0.12, n) + np.where(idade < 35, 0.10, np.where(idade > 55, -0.08, 0)),
        "taxa_anual": np.array([PEDIDOS_ANO[s] for s in segmento]) * rng.lognormal(0, 0.35, n),
    })
    inicio_ativo = np.maximum((cadastro - DATA_INICIO).days, 0)
    churn_dia = np.full(n, dias_periodo + 1)
    for i, s in enumerate(segmento):
        restante = dias_periodo - inicio_ativo[i]
        if restante > 120 and rng.random() < PROB_CHURN[s]:
            churn_dia[i] = inicio_ativo[i] + rng.integers(60, restante)
    ocultos["inicio_ativo"] = inicio_ativo
    ocultos["churn_dia"] = churn_dia
    return clientes, ocultos


# --------------------------------------------------------------------------
# Tabelas de fato
# --------------------------------------------------------------------------
def gerar_pedidos(clientes: pd.DataFrame, ocultos: pd.DataFrame, lojas: pd.DataFrame,
                  rng: np.random.Generator) -> pd.DataFrame:
    dias = pd.date_range(DATA_INICIO, DATA_FIM, freq="D")
    n_dias = len(dias)
    idx_dia = np.arange(n_dias)
    bf = janelas_black_friday(dias)
    nov_dez = np.isin(dias.month, [11, 12])

    fator_dow = np.where(dias.day_of_week == 5, 1.2, np.where(dias.day_of_week == 6, 0.9, 1.0))
    tendencia = 1 + 0.08 * idx_dia / 365
    fator_geral = FATOR_MES[dias.month - 1] * fator_dow * tendencia * np.where(bf, 2.5, 1.0)
    # Clientes "promocionais" compram pouco no ano e muito em novembro/dezembro
    fator_promo = fator_geral * np.where(bf, 3.0, np.where(nov_dez, 2.0, 0.5))

    promo = (ocultos["segmento"] == "promocional").to_numpy()
    ativo = ((idx_dia[:, None] >= ocultos["inicio_ativo"].to_numpy()[None, :])
             & (idx_dia[:, None] < ocultos["churn_dia"].to_numpy()[None, :]))
    lam = (ocultos["taxa_anual"].to_numpy()[None, :] / 365
           * np.where(promo[None, :], fator_promo[:, None], fator_geral[:, None]) * ativo)
    contagem = rng.poisson(lam.astype(np.float32))

    d_idx, c_idx = np.nonzero(contagem)
    repeticoes = contagem[d_idx, c_idx]
    d_idx = np.repeat(d_idx, repeticoes)
    c_idx = np.repeat(c_idx, repeticoes)
    ordem = np.lexsort((c_idx, d_idx))
    d_idx, c_idx = d_idx[ordem], c_idx[ordem]
    n_ped = len(d_idx)

    # Canal: participação online cresce de ~30% para ~55% e sobe na Black Friday
    p_online = np.clip(0.30 + 0.25 * d_idx / n_dias + ocultos["pref_online"].to_numpy()[c_idx]
                       + np.where(bf[d_idx], 0.08, 0), 0.05, 0.95)
    online = rng.random(n_ped) < p_online

    # Loja física: preferencialmente a da mesma UF; senão outra aberta da região
    fisicas = lojas[lojas["tipo_loja"] == "Física"].copy()
    fisicas["abertura_idx"] = (pd.to_datetime(fisicas["data_abertura"]) - DATA_INICIO).dt.days
    uf_cli = clientes["uf"].to_numpy()
    reg_cli = ocultos["regiao"].to_numpy()
    id_loja = np.full(n_ped, ID_LOJA_ONLINE)
    for i in np.where(~online)[0]:
        c, d = c_idx[i], d_idx[i]
        abertas = fisicas[(fisicas["regiao"] == reg_cli[c]) & (fisicas["abertura_idx"] <= d)]
        if abertas.empty:
            continue  # sem loja aberta na região -> compra online
        pesos = np.where(abertas["uf"].to_numpy() == uf_cli[c], 6.0, 1.0)
        id_loja[i] = rng.choice(abertas["id_loja"].to_numpy(), p=pesos / pesos.sum())
    online = id_loja == ID_LOJA_ONLINE

    pagamento = np.where(
        online,
        rng.choice(["Pix", "Cartão de Crédito", "Boleto"], n_ped, p=[0.35, 0.55, 0.10]),
        rng.choice(["Cartão de Crédito", "Cartão de Débito", "Pix", "Dinheiro"], n_ped,
                   p=[0.50, 0.25, 0.20, 0.05]))

    return pd.DataFrame({
        "id_pedido": np.arange(1, n_ped + 1),
        "id_cliente": clientes["id_cliente"].to_numpy()[c_idx],
        "id_loja": id_loja,
        "data_pedido": dias[d_idx],
        "forma_pagamento": pagamento,
        "_dia_idx": d_idx,
        "_cli_idx": c_idx,
        "_bf": bf[d_idx],
    })


def gerar_itens(pedidos: pd.DataFrame, produtos: pd.DataFrame, ocultos: pd.DataFrame,
                rng: np.random.Generator) -> pd.DataFrame:
    n_itens_ped = np.clip(rng.geometric(0.55, len(pedidos)), 1, 5)
    ped_idx = np.repeat(np.arange(len(pedidos)), n_itens_ped)
    n = len(ped_idx)
    meses = pedidos["data_pedido"].dt.month.to_numpy()[ped_idx]
    bf = pedidos["_bf"].to_numpy()[ped_idx]
    promo = (ocultos["segmento"].to_numpy()[pedidos["_cli_idx"].to_numpy()] == "promocional")[ped_idx]

    # Mix de categorias por mês (datas comemorativas)
    nomes_cat = list(CATEGORIAS)
    base = np.array([CATEGORIAS[c]["pop"] for c in nomes_cat])
    ajuste = np.ones((12, len(nomes_cat)))
    ic = {c: i for i, c in enumerate(nomes_cat)}
    for m in (11, 12):
        ajuste[m - 1, ic["Eletrônicos"]] = 1.6
        ajuste[m - 1, ic["Informática"]] = 1.4
    ajuste[0, ic["Esporte e Lazer"]] = 1.5
    ajuste[0, ic["Informática"]] = ajuste[1, ic["Informática"]] = 1.3
    ajuste[4, ic["Beleza e Saúde"]] = 1.6
    ajuste[4, ic["Moda"]] = 1.3
    ajuste[7, ic["Eletrônicos"]] = ajuste[7, ic["Esporte e Lazer"]] = 1.25
    probs_mes = base * ajuste
    cat_idx = escolha_por_linha(rng, probs_mes[meses - 1])

    # Produto dentro da categoria: itens mais baratos vendem mais
    id_produto = np.empty(n, dtype=int)
    for i, cat in enumerate(nomes_cat):
        sel = cat_idx == i
        prods = produtos[produtos["categoria"] == cat]
        pesos = prods["preco_lista"].to_numpy() ** -0.6
        id_produto[sel] = rng.choice(prods["id_produto"].to_numpy(), size=sel.sum(), p=pesos / pesos.sum())
    prod = produtos.set_index("id_produto").loc[id_produto]
    preco = prod["preco_lista"].to_numpy()

    quantidade = np.where(preco < 100, 1 + rng.binomial(2, 0.3, n), 1 + (rng.random(n) < 0.05))

    # Descontos: comuns no ano, agressivos na Black Friday
    desc_normal = rng.choice([0, 0.05, 0.10, 0.15], n, p=[0.55, 0.25, 0.15, 0.05])
    desc_fim_ano = rng.choice([0, 0.05, 0.10, 0.15, 0.20], n, p=[0.35, 0.25, 0.20, 0.12, 0.08])
    desc_bf = rng.choice([0.15, 0.20, 0.25, 0.30], n, p=[0.25, 0.30, 0.30, 0.15])
    tecnologia = np.isin(cat_idx, [ic["Eletrônicos"], ic["Informática"]])
    desc_bf = np.where(tecnologia, desc_bf + 0.05, desc_bf)
    desconto = np.where(bf & (rng.random(n) < 0.85), desc_bf,
                        np.where(np.isin(meses, [11, 12]), desc_fim_ano, desc_normal))
    desconto = np.round(np.minimum(desconto + np.where(promo, 0.05, 0), 0.40), 2)

    return pd.DataFrame({
        "id_item": np.arange(1, n + 1),
        "id_pedido": pedidos["id_pedido"].to_numpy()[ped_idx],
        "id_produto": id_produto,
        "quantidade": quantidade,
        "preco_unitario": preco,
        "desconto_pct": desconto,
        "_categoria": np.array(nomes_cat)[cat_idx],
    })


def completar_pedidos(pedidos: pd.DataFrame, itens: pd.DataFrame, clientes: pd.DataFrame,
                      rng: np.random.Generator) -> pd.DataFrame:
    """Define status (entregue/cancelado/devolvido) e frete a partir dos itens."""
    itens = itens.assign(
        valor=itens["quantidade"] * itens["preco_unitario"] * (1 - itens["desconto_pct"]),
        p_devol=itens["_categoria"].map({c: v["devol"] for c, v in CATEGORIAS.items()}))
    por_pedido = itens.groupby("id_pedido").agg(subtotal=("valor", "sum"), p_devol=("p_devol", "max"))
    pedidos = pedidos.merge(por_pedido, left_on="id_pedido", right_index=True)
    online = (pedidos["id_loja"] == ID_LOJA_ONLINE).to_numpy()
    n = len(pedidos)

    p_cancel = 0.03 + 0.015 * online
    p_devol = pedidos["p_devol"].to_numpy() + 0.02 * online
    u = rng.random(n)
    status = np.where(u < p_cancel, "Cancelado",
                      np.where(rng.random(n) < p_devol, "Devolvido", "Entregue"))

    regiao_cli = clientes.set_index("id_cliente").loc[pedidos["id_cliente"], "uf"].map(
        {uf: v[0] for uf, v in UFS.items()}).to_numpy()
    frete = np.where(pedidos["subtotal"].to_numpy() >= 299, 0.0, rng.uniform(12, 39.9, n))
    frete = frete * np.where(np.isin(regiao_cli, ["Norte", "Nordeste"]), 1.3, 1.0)
    frete = np.where(online, np.round(frete, 2), 0.0)

    pedidos["status"] = status
    pedidos["valor_frete"] = frete
    pedidos["data_pedido"] = pedidos["data_pedido"].dt.strftime("%Y-%m-%d")
    return pedidos[["id_pedido", "id_cliente", "id_loja", "data_pedido", "forma_pagamento",
                    "status", "valor_frete"]]


# --------------------------------------------------------------------------
# Inserção controlada de problemas de qualidade ("sujeira")
# --------------------------------------------------------------------------
def inserir_problemas(clientes, produtos, pedidos, itens, rng):
    reg = {}

    def amostra(df, frac):
        return rng.choice(df.index.to_numpy(), size=max(1, int(len(df) * frac)), replace=False)

    # CLIENTES
    c = clientes.copy()
    i = amostra(c, 0.08)
    c.loc[i, "uf"] = [rng.choice([u.lower(), f" {u} ", f"{u} "]) for u in c.loc[i, "uf"]]
    reg["clientes_uf_fora_do_padrao"] = len(i)
    i = amostra(c, 0.08)
    c.loc[i, "cidade"] = [rng.choice([x.upper(), sem_acento(x), x.lower()]) for x in c.loc[i, "cidade"]]
    reg["clientes_cidade_fora_do_padrao"] = len(i)
    i = amostra(c, 0.03)
    c.loc[i, "email"] = None
    reg["clientes_email_nulo"] = len(i)
    i = amostra(c, 0.02)
    c.loc[i, "data_nascimento"] = None
    reg["clientes_nascimento_nulo"] = len(i)
    i = amostra(c, 0.003)
    c.loc[i, "data_nascimento"] = "1900-01-01"
    reg["clientes_nascimento_invalido"] = len(i)
    dup = c.loc[amostra(c, 0.015)]
    reg["clientes_linhas_duplicadas"] = len(dup)
    c = pd.concat([c, dup]).sample(frac=1, random_state=int(rng.integers(1e9))).reset_index(drop=True)

    # PRODUTOS
    p = produtos.copy().astype({"preco_lista": object})
    i = amostra(p, 0.10)
    p.loc[i, "categoria"] = [rng.choice([x.upper(), x.lower(), sem_acento(x)]) for x in p.loc[i, "categoria"]]
    reg["produtos_categoria_fora_do_padrao"] = len(i)
    i = amostra(p, 0.06)
    p.loc[i, "preco_lista"] = [f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                               for v in p.loc[i, "preco_lista"]]
    reg["produtos_preco_formato_brasileiro"] = len(i)
    i = amostra(p, 0.025)
    p.loc[i, "custo_unitario"] = None
    reg["produtos_custo_nulo"] = len(i)

    # PEDIDOS
    pe = pedidos.copy()
    i = amostra(pe, 0.15)
    pe.loc[i, "data_pedido"] = pd.to_datetime(pe.loc[i, "data_pedido"]).dt.strftime("%d/%m/%Y")
    reg["pedidos_data_formato_dd_mm_aaaa"] = len(i)
    i = amostra(pe, 0.06)
    pe.loc[i, "status"] = [rng.choice([s.lower(), s.upper(), f"{s} "]) for s in pe.loc[i, "status"]]
    reg["pedidos_status_fora_do_padrao"] = len(i)
    com_frete = pe.index[pe["valor_frete"] > 0].to_numpy()
    i = rng.choice(com_frete, size=max(1, int(len(com_frete) * 0.01)), replace=False)
    pe.loc[i, "valor_frete"] = -pe.loc[i, "valor_frete"]
    reg["pedidos_frete_negativo"] = len(i)
    i = amostra(pe, 0.002)
    pe.loc[i, "id_cliente"] = rng.integers(90000, 99999, len(i))
    reg["pedidos_cliente_inexistente"] = len(i)
    dup = pe.loc[amostra(pe, 0.008)]
    reg["pedidos_linhas_duplicadas"] = len(dup)
    pe = pd.concat([pe, dup]).sort_values("id_pedido", kind="stable").reset_index(drop=True)

    # ITENS
    it = itens.drop(columns="_categoria").astype({"desconto_pct": object, "quantidade": object})
    i = amostra(it, 0.002)
    it.loc[i, "quantidade"] = rng.choice([0, -1], len(i))
    reg["itens_quantidade_zero_ou_negativa"] = len(i)
    i = amostra(it, 0.0005)
    it.loc[i, "quantidade"] = 999
    reg["itens_quantidade_outlier_999"] = len(i)
    i = amostra(it, 0.005)
    it.loc[i, "preco_unitario"] = None
    reg["itens_preco_nulo"] = len(i)
    i = amostra(it, 0.04)
    it.loc[i, "desconto_pct"] = [rng.choice([f"{round(v * 100)}%", str(round(v * 100))])
                                 for v in it.loc[i, "desconto_pct"]]
    reg["itens_desconto_formato_texto"] = len(i)
    dup = it.loc[amostra(it, 0.005)]
    reg["itens_linhas_duplicadas"] = len(dup)
    it = pd.concat([it, dup]).sort_values("id_item", kind="stable").reset_index(drop=True)

    return c, p, pe, it, reg


# --------------------------------------------------------------------------
def main(seed: int = 42, n_clientes: int = 8000, saida: Path | None = None) -> dict:
    saida = Path(saida or RAIZ / "data" / "raw")
    saida.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    fake = Faker("pt_BR")
    Faker.seed(seed)

    lojas = gerar_lojas()
    produtos = gerar_produtos(rng)
    clientes, ocultos = gerar_clientes(n_clientes, rng, fake)
    pedidos = gerar_pedidos(clientes, ocultos, lojas, rng)
    itens = gerar_itens(pedidos, produtos, ocultos, rng)
    pedidos = completar_pedidos(pedidos, itens, clientes, rng)

    clientes_r, produtos_r, pedidos_r, itens_r, problemas = inserir_problemas(
        clientes, produtos, pedidos, itens, rng)

    lojas.to_csv(saida / "lojas.csv", index=False, encoding="utf-8")
    produtos_r.to_csv(saida / "produtos.csv", index=False, encoding="utf-8")
    clientes_r.to_csv(saida / "clientes.csv", index=False, encoding="utf-8")
    pedidos_r.to_csv(saida / "pedidos.csv", index=False, encoding="utf-8")
    itens_r.to_csv(saida / "itens_pedido.csv", index=False, encoding="utf-8")

    resumo = {
        "seed": seed,
        "periodo": [str(DATA_INICIO.date()), str(DATA_FIM.date())],
        "linhas_geradas_sem_problemas": {
            "lojas": len(lojas), "produtos": len(produtos), "clientes": len(clientes),
            "pedidos": len(pedidos), "itens_pedido": len(itens)},
        "problemas_inseridos": problemas,
    }
    (saida / "_problemas_inseridos.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False),
                                                     encoding="utf-8")
    return resumo


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Gera a base sintética da Mercatto.")
    ap.add_argument("--seed", type=int, default=42, help="semente aleatória (reprodutibilidade)")
    ap.add_argument("--clientes", type=int, default=8000, help="quantidade de clientes")
    ap.add_argument("--saida", type=Path, default=None, help="pasta de saída (padrão: data/raw)")
    args = ap.parse_args()
    r = main(args.seed, args.clientes, args.saida)
    print(json.dumps(r, indent=2, ensure_ascii=False))
