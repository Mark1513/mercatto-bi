"""
Validação da qualidade dos dados — antes (raw) e depois (processed) do ETL.

Gera:
    reports/relatorio_qualidade.md   (relatório legível)
    reports/qualidade.json           (resultado dos testes, usado no dashboard)

Cada teste da base tratada deve resultar em 0 problemas; se algum falhar,
o script termina com código de erro 1 (o pipeline para).

Execução:
    python -m src.validacao
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
RAW = RAIZ / "data" / "raw"
DB_PATH = RAIZ / "data" / "processed" / "bi.db"
REPORTS = RAIZ / "reports"

# (descrição, dimensão de qualidade, SQL que conta registros com problema)
TESTES = [
    # Unicidade das chaves primárias
    ("PK única em dim_cliente", "Unicidade",
     "SELECT COUNT(*) - COUNT(DISTINCT id_cliente) FROM dim_cliente"),
    ("PK única em dim_produto", "Unicidade",
     "SELECT COUNT(*) - COUNT(DISTINCT id_produto) FROM dim_produto"),
    ("PK única em fato_pedido", "Unicidade",
     "SELECT COUNT(*) - COUNT(DISTINCT id_pedido) FROM fato_pedido"),
    ("PK única em fato_item_pedido", "Unicidade",
     "SELECT COUNT(*) - COUNT(DISTINCT id_item) FROM fato_item_pedido"),
    # Integridade referencial
    ("Pedido sem cliente válido", "Integridade",
     "SELECT COUNT(*) FROM fato_pedido p LEFT JOIN dim_cliente c USING(id_cliente) WHERE c.id_cliente IS NULL"),
    ("Pedido sem loja válida", "Integridade",
     "SELECT COUNT(*) FROM fato_pedido p LEFT JOIN dim_loja l USING(id_loja) WHERE l.id_loja IS NULL"),
    ("Pedido sem data no calendário", "Integridade",
     "SELECT COUNT(*) FROM fato_pedido p LEFT JOIN dim_calendario d ON d.data = p.data_pedido WHERE d.data IS NULL"),
    ("Item sem pedido válido", "Integridade",
     "SELECT COUNT(*) FROM fato_item_pedido i LEFT JOIN fato_pedido p USING(id_pedido) WHERE p.id_pedido IS NULL"),
    ("Item sem produto válido", "Integridade",
     "SELECT COUNT(*) FROM fato_item_pedido i LEFT JOIN dim_produto p USING(id_produto) WHERE p.id_produto IS NULL"),
    ("Pedido sem nenhum item", "Integridade",
     "SELECT COUNT(*) FROM fato_pedido p WHERE NOT EXISTS (SELECT 1 FROM fato_item_pedido i WHERE i.id_pedido = p.id_pedido)"),
    # Completude
    ("Campos obrigatórios nulos em fato_pedido", "Completude",
     "SELECT COUNT(*) FROM fato_pedido WHERE id_cliente IS NULL OR id_loja IS NULL OR data_pedido IS NULL OR status IS NULL"),
    ("Preço ou custo nulo em itens/produtos", "Completude",
     "SELECT (SELECT COUNT(*) FROM fato_item_pedido WHERE preco_unitario IS NULL OR receita_liquida IS NULL)"
     " + (SELECT COUNT(*) FROM dim_produto WHERE custo_unitario IS NULL OR preco_lista IS NULL)"),
    ("Cliente sem região", "Completude",
     "SELECT COUNT(*) FROM dim_cliente WHERE regiao IS NULL"),
    # Validade / domínio
    ("Quantidade fora de 1..20", "Validade",
     "SELECT COUNT(*) FROM fato_item_pedido WHERE quantidade < 1 OR quantidade > 20"),
    ("Desconto fora de 0%..90%", "Validade",
     "SELECT COUNT(*) FROM fato_item_pedido WHERE desconto_pct < 0 OR desconto_pct > 0.9"),
    ("Preço unitário ≤ 0", "Validade",
     "SELECT COUNT(*) FROM fato_item_pedido WHERE preco_unitario <= 0"),
    ("Frete negativo", "Validade",
     "SELECT COUNT(*) FROM fato_pedido WHERE valor_frete < 0"),
    ("Status fora do domínio", "Validade",
     "SELECT COUNT(*) FROM fato_pedido WHERE status NOT IN ('Entregue','Cancelado','Devolvido')"),
    ("UF fora do padrão (2 letras maiúsculas)", "Validade",
     "SELECT COUNT(*) FROM dim_cliente WHERE uf <> UPPER(TRIM(uf)) OR LENGTH(uf) <> 2"),
    # Consistência entre tabelas / regras de negócio
    ("Pedido anterior ao cadastro do cliente", "Consistência",
     "SELECT COUNT(*) FROM fato_pedido p JOIN dim_cliente c USING(id_cliente) WHERE p.data_pedido < c.data_cadastro"),
    ("Venda em loja física antes da inauguração", "Consistência",
     "SELECT COUNT(*) FROM fato_pedido p JOIN dim_loja l USING(id_loja) WHERE p.data_pedido < l.data_abertura"),
    ("Total do pedido ≠ soma dos itens (tolerância R$ 0,05)", "Consistência",
     "SELECT COUNT(*) FROM fato_pedido p JOIN (SELECT id_pedido, SUM(receita_liquida) s FROM fato_item_pedido "
     "GROUP BY id_pedido) i USING(id_pedido) WHERE ABS(p.receita_liquida - i.s) > 0.05"),
    ("Receita líquida ≠ bruta − desconto", "Consistência",
     "SELECT COUNT(*) FROM fato_item_pedido WHERE ABS(receita_bruta - valor_desconto - receita_liquida) > 0.02"),
]


def perfil_bruto() -> pd.DataFrame:
    """Perfil dos CSV brutos: linhas, duplicatas exatas e nulos por tabela."""
    linhas = []
    for nome in ("clientes", "produtos", "lojas", "pedidos", "itens_pedido"):
        df = pd.read_csv(RAW / f"{nome}.csv", dtype=str)
        nulos = df.isna().sum()
        linhas.append({
            "tabela": nome,
            "linhas": len(df),
            "duplicatas_exatas": int(df.duplicated().sum()),
            "celulas_nulas": int(nulos.sum()),
            "colunas_com_nulos": ", ".join(f"{c} ({n})" for c, n in nulos.items() if n) or "—",
        })
    return pd.DataFrame(linhas)


def main() -> bool:
    REPORTS.mkdir(exist_ok=True)
    bruto = perfil_bruto()
    with sqlite3.connect(DB_PATH) as con:
        resultados = [{"teste": t, "dimensao": d, "problemas": int(con.execute(sql).fetchone()[0])}
                      for t, d, sql in TESTES]
        volumes = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                   for t in ("dim_calendario", "dim_cliente", "dim_produto", "dim_loja",
                             "fato_pedido", "fato_item_pedido")}
        nulos_faixa = con.execute(
            "SELECT COUNT(*) FROM dim_cliente WHERE faixa_etaria = 'Não informado'").fetchone()[0]
        custo_imputado = con.execute("SELECT SUM(custo_imputado) FROM dim_produto").fetchone()[0]

    res = pd.DataFrame(resultados)
    res["resultado"] = res["problemas"].map(lambda n: "OK" if n == 0 else "FALHOU")
    ok = bool((res["problemas"] == 0).all())

    log_etl = json.loads((REPORTS / "log_etl.json").read_text(encoding="utf-8"))
    inseridos = json.loads((RAW / "_problemas_inseridos.json").read_text(encoding="utf-8"))

    md = ["# Relatório de qualidade dos dados — Mercatto", "",
          f"**Resultado geral:** {'✅ todos os testes passaram' if ok else '❌ há testes com falha'} "
          f"({(res['problemas'] == 0).sum()}/{len(res)})", "",
          "## 1. Perfil da base bruta (antes do ETL)", "", bruto.to_markdown(index=False), "",
          "## 2. Problemas inseridos pelo gerador × tratados no ETL", "",
          "O gerador insere problemas de propósito (registrados em `data/raw/_problemas_inseridos.json`). "
          "O ETL detecta e trata cada um (registrado em `reports/log_etl.json`).", "",
          "| Problema inserido | Qtde | Tratamento no ETL |", "|---|---:|---|"]
    tratamento = {
        "clientes_uf_fora_do_padrao": "UF com TRIM + UPPER",
        "clientes_cidade_fora_do_padrao": "unificação pela grafia mais frequente (sem acento/caixa)",
        "clientes_email_nulo": "campo não usado na análise; removido da camada analítica (LGPD)",
        "clientes_nascimento_nulo": "faixa etária = 'Não informado'",
        "clientes_nascimento_invalido": "idade fora de 16–100 anos anulada",
        "clientes_linhas_duplicadas": "remoção de duplicatas exatas",
        "produtos_categoria_fora_do_padrao": "unificação pela grafia mais frequente",
        "produtos_preco_formato_brasileiro": "conversão '1.299,90' → 1299.90",
        "produtos_custo_nulo": "imputação: preço × (1 − margem mediana da categoria)",
        "pedidos_data_formato_dd_mm_aaaa": "conversão DD/MM/AAAA → AAAA-MM-DD",
        "pedidos_status_fora_do_padrao": "TRIM + capitalização",
        "pedidos_frete_negativo": "valor absoluto (erro de sinal)",
        "pedidos_cliente_inexistente": "pedido e itens removidos (FK órfã)",
        "pedidos_linhas_duplicadas": "remoção de duplicatas exatas",
        "itens_quantidade_zero_ou_negativa": "item removido",
        "itens_quantidade_outlier_999": "item removido (qtde > 20)",
        "itens_preco_nulo": "imputação com o preço de lista do produto",
        "itens_desconto_formato_texto": "'15%' ou '15' → 0,15",
        "itens_linhas_duplicadas": "remoção de duplicatas exatas",
    }
    for k, v in inseridos["problemas_inseridos"].items():
        md.append(f"| `{k}` | {v} | {tratamento.get(k, '')} |")

    md += ["", "Pedidos que ficaram sem nenhum item válido após a limpeza também foram removidos "
           f"({log_etl.get('pedidos_sem_itens_validos_removidos', 0)}).", "",
           "## 3. Testes na base tratada (depois do ETL)", "",
           res[["dimensao", "teste", "problemas", "resultado"]].to_markdown(index=False), "",
           "## 4. Volumes finais carregados", "",
           pd.Series(volumes, name="linhas").to_frame().to_markdown(), "",
           "## 5. Limitações conhecidas", "",
           f"- {nulos_faixa} clientes sem faixa etária (nascimento ausente ou inválido) — mantidos, "
           "mas aparecem como 'Não informado'.",
           f"- {custo_imputado} produtos com custo imputado — a margem desses itens é estimada.",
           "- Itens com preço nulo receberam o preço de lista; se houve desconto negociado fora do "
           "sistema, a receita desses itens pode estar levemente superestimada.",
           "- Quantidades acima de 20 foram tratadas como erro; em vendas corporativas reais essa regra "
           "precisaria ser revista.",
           "- Os dados são sintéticos: os padrões foram simulados a partir de premissas do cenário e "
           "não representam uma empresa real.", ""]
    (REPORTS / "relatorio_qualidade.md").write_text("\n".join(md), encoding="utf-8")
    (REPORTS / "qualidade.json").write_text(json.dumps({
        "ok": ok, "testes": resultados, "volumes": volumes,
        "perfil_bruto": bruto.to_dict(orient="records"),
        "problemas_inseridos": inseridos["problemas_inseridos"]}, indent=2, ensure_ascii=False),
        encoding="utf-8")

    print(res[["dimensao", "teste", "problemas", "resultado"]].to_string(index=False))
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
