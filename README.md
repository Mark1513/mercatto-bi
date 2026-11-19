# Mercatto — Solução de Business Intelligence

Prova prática de **Desenvolvimento de Business Intelligence**: uma solução completa, da geração de uma base
sintética por código até um dashboard interativo com recomendações gerenciais, para a Mercatto, uma
varejista omnicanal **fictícia** (10 lojas físicas + e-commerce, 2023–2025).

**Integrantes:** _preencher_

## Como executar

Requisitos: **Python 3.11 ou superior**.

```bash
# 1. Criar e ativar um ambiente virtual (Windows)
python -m venv .venv
.venv\Scripts\activate
#    (Linux/macOS: source .venv/bin/activate)

# 2. Instalar as bibliotecas
pip install -r requirements.txt

# 3. Rodar o pipeline completo: gerar base → ETL → validar → analisar (~25 s)
python run_all.py

# 4. Abrir o dashboard (abre no navegador em http://localhost:8501)
streamlit run dashboard/app.py
```

Opcional: `python run_all.py --seed 7 --clientes 5000` gera outra base com o mesmo processo. Cada etapa também
roda separada: `python -m src.gerar_base`, `python -m src.etl`, `python -m src.validacao`, `python -m src.analise`.

> **Windows:** se aparecer o erro `DLL load failed ... The filename or extension is too long`, o caminho da
> pasta está longo demais. Crie o ambiente virtual num caminho curto, por exemplo
> `python -m venv C:\venvs\bi`.

## Publicar o dashboard na internet (Streamlit Community Cloud)

A pasta `data/` não vai para o GitHub (está no `.gitignore`). Na primeira vez que o dashboard abre no
servidor, ele mesmo roda o pipeline completo (≈ 30–60 s) e gera a base com a semente 42. Por isso os números
online são idênticos aos locais, e isso ainda demonstra a reprodutibilidade.

1. Crie um repositório no GitHub e envie esta pasta (a raiz do repositório é esta pasta, `projeto_bi`).
2. Acesse **share.streamlit.io**, entre com a conta do GitHub e clique em **Create app → Deploy a public app
   from GitHub**.
3. Preencha:
   - **Repository:** `seu-usuario/nome-do-repositorio`
   - **Branch:** `main`
   - **Main file path:** `dashboard/app.py`
   - **App URL:** escolha um nome, por exemplo `mercatto-bi`
   - Em **Advanced settings → Python version**, escolha **3.12**
4. Clique em **Deploy**. A instalação das bibliotecas leva alguns minutos. Depois o link
   (`https://mercatto-bi.streamlit.app`) abre em qualquer computador ou celular.

Observações:
- Depois de alguns dias sem acesso, o app "dorme". Basta clicar em *"Yes, get this app back up"* para ele
  voltar. A base é gerada de novo, com os mesmos números.
- Cada `git push` no repositório atualiza o app automaticamente.
- O link é público. Aqui não há problema porque os dados são 100% fictícios.

## Estrutura

```
projeto_bi/
├── run_all.py                 # executa o fluxo completo
├── requirements.txt
├── src/
│   ├── gerar_base.py          # gerador da base sintética (seed fixa, 5 tabelas)
│   ├── etl.py                 # limpeza, padronização, transformação, modelo estrela, carga no SQLite
│   ├── validacao.py           # 23 testes de qualidade + relatório
│   └── analise.py             # KPIs, RFM + K-means, previsão Holt-Winters, anomalias
├── notebooks/analise.ipynb    # análise exploratória e técnicas, com gráficos e comentários
├── dashboard/app.py           # dashboard Streamlit (6 abas, filtros, KPIs com variação)
├── data/
│   ├── raw/                   # CSV brutos gerados (com problemas de qualidade inseridos)
│   └── processed/             # bi.db (SQLite) + CSV tratados (prontos para o Power BI, se quiser)
├── reports/                   # relatorio_qualidade.md, log_etl.json, resultados_analise.json
└── docs/
    ├── 01_planejamento.md     # cenário, problema, usuários, perguntas, KPIs
    ├── 02_dicionario_dados.md # modelo estrela, granularidade, volume, dicionário
    ├── 03_insights_recomendacoes.md  # 7 insights, 5 recomendações, limitações, LGPD
    └── 04_roteiro_defesa.md   # roteiro da demonstração e perguntas prováveis
```

## Onde está cada item do barema

| Critério do barema | Pontos | Onde está |
|---|---:|---|
| **Unidade 1 — Planejamento** | **600** | |
| Cenário, problema e objetivos | 150 | `docs/01_planejamento.md` §1.1–1.3 |
| Usuários e perguntas gerenciais | 150 | `docs/01_planejamento.md` §1.4–1.5 |
| KPIs: fórmula, unidade, interpretação | 200 | `docs/01_planejamento.md` §1.6 |
| Coerência problema × dados × indicadores | 100 | `docs/01_planejamento.md` §1.7 |
| **Unidade 2 — Base, modelagem, ETL e qualidade** | **1.200** | |
| Código gerador funcional e reproduzível | 250 | `src/gerar_base.py` (seed, CLI), `run_all.py` |
| ≥ 4 tabelas e definição de chaves | 200 | 5 tabelas brutas → 6 no modelo estrela; DDL em `src/etl.py` |
| Relacionamentos e granularidade | 200 | `docs/02_dicionario_dados.md` §2.2 |
| Variedade, plausibilidade e volume | 150 | `docs/02_dicionario_dados.md` §2.3 |
| ETL: limpeza, padronização, transformação, integração | 250 | `src/etl.py`, `reports/log_etl.json` |
| Dicionário de dados e validação da qualidade | 150 | `docs/02_dicionario_dados.md`, `src/validacao.py`, `reports/relatorio_qualidade.md` |
| **Unidade 3 — Análise** | **900** | |
| Análise exploratória e estatística descritiva | 150 | `notebooks/analise.ipynb` §1–2 |
| Cálculos, agregações e comparações | 200 | notebook §3–7, `src/analise.py` |
| Técnica analítica pertinente | 250 | **RFM + K-means**, **previsão Holt-Winters**, **anomalias** (notebook §8–10) |
| Avaliação de métricas e limitações | 150 | silhouette, cotovelo, MAPE com origem móvel e baseline; notebook §11 |
| Padrões, tendências, anomalias, oportunidades | 150 | `docs/03_insights_recomendacoes.md` §3.2 |
| **Unidade 4 — Visualização e decisão** | **700** | |
| Escolha de gráficos e organização visual | 150 | `dashboard/app.py` |
| Dashboard funcional, filtros e navegação | 200 | 5 filtros, 6 abas, KPIs com Δ vs. período anterior |
| Insights sustentados por dados | 150 | `docs/03_insights_recomendacoes.md` §3.2 (7 insights) |
| Recomendações viáveis e fundamentadas | 150 | `docs/03_insights_recomendacoes.md` §3.3 (5 recomendações com metas) |
| Qualidade, privacidade e segurança | 50 | `docs/03_insights_recomendacoes.md` §3.5, aba *Qualidade e governança* |
| **Integração e defesa** | **600** | |
| Integração do fluxo completo | 150 | `run_all.py` → dashboard |
| Organização e instruções | 100 | este README |
| Demonstração prática | 150 | `docs/04_roteiro_defesa.md` §4.1 |
| Domínio técnico e respostas | 200 | `docs/04_roteiro_defesa.md` §4.2 |

## Tecnologias

Python · pandas · NumPy · Faker · SQLite · scikit-learn (K-means) · statsmodels (Holt-Winters) ·
Streamlit · Plotly · Jupyter/matplotlib
