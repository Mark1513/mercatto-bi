# 1. Planejamento do negócio e requisitos de BI

## 1.1 Cenário

A **Mercatto** é uma varejista omnicanal **fictícia** que vende eletrônicos, informática, casa e cozinha, moda,
esporte e beleza. Ela opera:

- **10 lojas físicas** nas cinco regiões do país (a loja de Recife foi inaugurada em 15/03/2024);
- **1 e-commerce** com entrega nacional;
- **120 produtos** em 6 categorias, cada um nas linhas *Essencial* e *Premium*.

O período analisado vai de **01/01/2023 a 31/12/2025** (36 meses).

## 1.2 Problema de negócio

A receita da Mercatto cresce todo ano, mas a diretoria não sabe se esse crescimento é **saudável e
sustentável**. As principais preocupações são:

1. **Rentabilidade:** a empresa investe pesado em descontos, sobretudo na Black Friday, e não sabe se essas
   campanhas dão lucro ou apenas volume.
2. **Retenção:** a base de clientes cresce, mas ninguém sabe quantos clientes antigos estão sendo perdidos nem
   quais valem um esforço de reativação.
3. **Devoluções:** a equipe de e-commerce percebe muitas devoluções, mas não sabe onde elas se concentram.
4. **Expansão:** é preciso decidir onde investir (canal online ou lojas, e em quais regiões).
5. **Planejamento:** o financeiro precisa de uma estimativa de receita do 1º semestre de 2026 para planejar
   estoque e caixa.

## 1.3 Objetivos da solução de BI

| # | Objetivo | Entregável |
|---|---|---|
| O1 | Centralizar os indicadores comerciais em um painel único e confiável | Dashboard + modelo estrela validado |
| O2 | Medir a rentabilidade dos descontos e da Black Friday | Análise de margem por faixa de desconto e evento |
| O3 | Identificar segmentos de clientes para ações de retenção | Segmentação RFM + K-means |
| O4 | Prever a receita mensal do 1º semestre de 2026 | Modelo Holt-Winters validado (MAPE) |
| O5 | Apoiar decisões de expansão por canal e região | Comparativos por canal, região e loja |
| O6 | Garantir dados de qualidade e uso responsável | ETL, testes de qualidade e diretrizes de LGPD |

## 1.4 Usuários da informação

| Usuário | O que precisa saber | Onde encontra |
|---|---|---|
| **Diretoria comercial** | Evolução da receita e da margem, crescimento e riscos | KPIs do topo, aba *Visão geral* |
| **Gerente de e-commerce** | Participação do online, devoluções, frete | *Visão geral*, *Produtos e margem* (devoluções) |
| **Gerentes regionais e de loja** | Desempenho da sua região ou loja | Filtro de região, aba *Regiões e lojas* |
| **Marketing / CRM** | Quem são os melhores clientes e quem está sendo perdido | Aba *Clientes (RFM)* |
| **Compras / gerentes de categoria** | Quais categorias geram margem e o efeito dos descontos | Aba *Produtos e margem* |
| **Financeiro / planejamento** | Receita esperada nos próximos meses | Aba *Previsão e anomalias* |

## 1.5 Perguntas gerenciais

| # | Pergunta | Usuário principal |
|---|---|---|
| P1 | Como evoluíram receita, pedidos e ticket médio de 2023 a 2025? Existe sazonalidade? | Diretoria |
| P2 | De qual canal e de qual região veio o crescimento? | Diretoria, regionais |
| P3 | Quais categorias geram receita e quais geram margem? | Compras |
| P4 | A Black Friday e os descontos altos são lucrativos? | Diretoria, compras |
| P5 | Quais categorias e canais concentram as devoluções? | E-commerce |
| P6 | Quem são os clientes mais valiosos e quais estamos perdendo? | Marketing/CRM |
| P7 | Quanto devemos faturar no 1º semestre de 2026? | Financeiro |
| P8 | Houve dias com vendas fora do padrão? Eles são explicados por eventos? | Diretoria, marketing |

## 1.6 KPIs

Regra geral: **receita e margem só contam pedidos com status "Entregue"**. Pedidos cancelados não foram
faturados e pedidos devolvidos tiveram o valor estornado.

| KPI | Objetivo | Fórmula | Unidade | Interpretação | Pergunta |
|---|---|---|---|---|---|
| **Receita líquida** | Medir o faturamento efetivo | Σ (qtde × preço unitário × (1 − desconto)) dos itens de pedidos entregues | R$ | Quanto maior, melhor; comparar com o período anterior | P1, P2 |
| **Crescimento da receita** | Medir a expansão | (Receita do período ÷ receita do período anterior) − 1 | % | > 0 indica crescimento | P1, P2 |
| **Margem bruta %** | Medir a rentabilidade | Σ (receita líquida − qtde × custo unitário) ÷ Σ receita líquida | % | Abaixo de 0 = venda com prejuízo; queda indica erosão por desconto ou mix | P3, P4 |
| **Ticket médio** | Valor por compra | Receita líquida ÷ nº de pedidos entregues | R$/pedido | Subida = clientes levam mais ou produtos mais caros | P1 |
| **Desconto médio %** | Medir a agressividade comercial | Σ valor do desconto ÷ Σ receita bruta | % | Subida sem aumento de margem absoluta é sinal de alerta | P4 |
| **Taxa de devolução** | Medir a insatisfação e o custo logístico | Pedidos devolvidos ÷ (pedidos entregues + devolvidos) | % | Quanto menor, melhor; comparar entre categorias e canais | P5 |
| **Taxa de cancelamento** | Medir a falha antes da entrega | Pedidos cancelados ÷ total de pedidos | % | Quanto menor, melhor | P5 |
| **Participação online** | Medir o peso do canal digital | Receita online ÷ receita total | % | Mostra a migração entre canais | P2 |
| **Clientes ativos** | Medir o tamanho da base | Nº de clientes distintos com pelo menos 1 pedido entregue no período | clientes | Subida = base crescendo | P1, P6 |
| **Taxa de recompra** | Medir a fidelização | Clientes com ≥ 2 pedidos entregues no período ÷ clientes ativos | % | Quanto maior, mais fiel a base | P6 |
| **Erro da previsão (MAPE)** | Medir a confiabilidade do modelo | média(\|real − previsto\| ÷ real) | % | < 10% é considerado bom para planejamento mensal | P7 |

## 1.7 Coerência entre problema, dados e indicadores

| Pergunta | Dados necessários | Tabelas | KPI ou técnica |
|---|---|---|---|
| P1 | Data, valor e status do pedido | `fato_pedido`, `dim_calendario` | Receita, crescimento, ticket, índice sazonal |
| P2 | Canal, loja, região do cliente | `fato_pedido`, `dim_loja`, `dim_cliente` | Receita por canal e região, participação online |
| P3 | Categoria, preço, custo | `fato_item_pedido`, `dim_produto` | Receita e margem % por categoria |
| P4 | Desconto por item, evento comercial | `fato_item_pedido`, `dim_calendario` | Margem por faixa de desconto, margem na Black Friday |
| P5 | Status, categoria, canal | `fato_pedido`, `fato_item_pedido`, `dim_produto` | Taxa de devolução |
| P6 | Histórico de pedidos por cliente | `fato_pedido`, `dim_cliente` | **RFM + K-means**, taxa de recompra |
| P7 | Receita mensal histórica | `fato_pedido` | **Holt-Winters** com validação de origem móvel (MAPE) |
| P8 | Receita diária, eventos | `fato_pedido`, `dim_calendario` | **Detecção de anomalias** (z-score robusto) |

Essa matriz guiou o desenho da base: cada campo gerado existe porque responde a pelo menos uma pergunta. Por
exemplo, `desconto_pct` existe para responder P4, `status` para P5 e `data_cadastro` para P6.
