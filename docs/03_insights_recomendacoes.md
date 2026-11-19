# 3. Insights, recomendações e limitações

Todos os números abaixo saem da base gerada com `seed = 42`, reproduzível com `python run_all.py`. Cada
insight indica onde a evidência pode ser conferida no dashboard (D) ou no notebook (N).

## 3.1 Resumo executivo

| KPI | 2023 | 2024 | 2025 |
|---|---:|---:|---:|
| Receita líquida | R$ 10,21 mi | R$ 15,48 mi | R$ 22,18 mi |
| Crescimento | — | +51,7% | +43,3% |
| Margem bruta | 23,6% | 23,4% | 23,5% |
| Ticket médio | R$ 884 | R$ 903 | R$ 906 |
| Pedidos entregues | 11.551 | 17.147 | 24.475 |
| Clientes ativos | 3.039 | 4.301 | 5.665 |
| Participação online | 37,5% | 47,6% | 54,6% |
| Taxa de devolução | 7,1% | 7,1% | 7,5% |
| Taxa de recompra | 72,6% | 72,9% | 76,0% |

## 3.2 Insights

### Insight 1: o crescimento veio de mais clientes, do canal online e do Nordeste, não de compras maiores
- A receita cresceu **117%** em dois anos (R$ 10,2 mi → R$ 22,2 mi). No mesmo período, os clientes ativos
  cresceram **86%** e o ticket médio só **2,5%** (R$ 884 → R$ 906). O motor é a **captação de clientes**.
- O canal online passou de **37,5% para 54,6%** da receita e hoje é o principal canal.
- O Nordeste cresceu **159%** (R$ 2,07 mi → R$ 5,37 mi) e sua participação subiu de 20,3% para 24,2%. O
  Sudeste cresceu 96% e perdeu participação (46,2% → 41,7%).
- A margem ficou praticamente estável (≈ 23,5%): o crescimento **não melhorou a rentabilidade**.
- *Evidência:* D › Visão geral e Regiões e lojas; N › seções 3 a 5.

### Insight 2: a Black Friday vende muito, mas dá prejuízo em Eletrônicos e Informática
- Nos 4 dias de Black Friday de 2025, a empresa faturou **R$ 1,02 mi** (4,6% da receita do ano), com margem de
  apenas **4,9%**, contra 23,5% no resto do ano.
- Na Black Friday a margem de **Eletrônicos foi −8,6%** e a de **Informática −3,3%**: essas categorias foram
  vendidas abaixo do custo. Elas somaram **64,5%** da receita da Black Friday de 2025.
- Itens de tecnologia com desconto acima de 20% têm margem de **−14,3%**; com desconto de até 15%, de
  **+15,4%**.
- O prejuízo bruto dos itens vendidos abaixo do custo na Black Friday cresce todo ano: R$ 29,1 mil (2023),
  R$ 54,1 mil (2024) e **R$ 62,4 mil (2025)**, totalizando **R$ 145,6 mil** no triênio.
- *Evidência:* D › Produtos e margem (mapa de calor e comparação Black Friday × resto); N › seção 6.

### Insight 3: Moda é a categoria mais rentável, mas devolve o dobro das outras
- Moda tem a **maior margem** (53,4%), mas a **maior taxa de devolução: 13,9%**, contra 6,4%–7,0% nas
  demais categorias.
- No online a devolução de Moda chega a **14,8%** (13,1% nas lojas), o que sugere problemas de tamanho e
  caimento que o cliente só percebe ao receber.
- Em 2025, **R$ 242 mil** em vendas de Moda foram devolvidas, além do custo logístico reverso.
- *Evidência:* D › Produtos e margem (devolução por categoria e canal); N › seção 7.

### Insight 4: 26% dos clientes geram 66% da receita, e um quarto da base está esfriando
- A segmentação RFM + K-means (k = 4, silhouette 0,34) encontrou quatro grupos:

| Segmento | Clientes | % clientes | % receita | Recência média | Pedidos/cliente | Receita/cliente |
|---|---:|---:|---:|---:|---:|---:|
| Campeões | 1.788 | 26,2% | 65,8% | 27 dias | 19,0 | R$ 17.619 |
| Em risco | 1.614 | 23,6% | 17,6% | 310 dias | 5,3 | R$ 5.224 |
| Regulares | 1.941 | 28,4% | 14,3% | 24 dias | 4,3 | R$ 3.538 |
| Hibernando | 1.491 | 21,8% | 2,2% | 341 dias | 1,5 | R$ 714 |

- O grupo **Em risco** já gerou **R$ 8,4 mi** em receita e comprava em média 5,3 vezes, mas está há cerca de
  10 meses sem comprar. É o grupo com maior potencial de retorno numa campanha de reativação.
- *Evidência:* D › Clientes (RFM); N › seção 8.

### Insight 5: a loja de Recife absorveu parte da demanda de Salvador, e o Ceará cresce sem loja
- Recife faturou R$ 0,78 mi no primeiro ano (2024, cerca de 9,5 meses) e **R$ 1,21 mi** em 2025.
- No ano da inauguração, **Salvador caiu 21%** (R$ 1,29 mi → R$ 1,02 mi), um sinal de canibalização:
  clientes de Pernambuco que iam a Salvador passaram a comprar em Recife. Mesmo assim, as lojas físicas do
  Nordeste somadas cresceram **82%** (R$ 1,29 mi → R$ 2,35 mi).
- Os clientes do **Ceará** (345) geraram **R$ 1,02 mi** em 2025 (+149% sobre 2023) sem nenhuma loja no estado,
  um valor próximo ao da loja de Salvador. O frete médio no Norte e no Nordeste (≈ R$ 11–12) é cerca de
  25% maior que no Sudeste (≈ R$ 9).
- *Evidência:* D › Regiões e lojas.

### Insight 6: a receita do 1º semestre de 2026 deve ficar perto de R$ 10,6 mi
- O modelo Holt-Winters (tendência aditiva e sazonalidade multiplicativa) teve **MAPE médio de 5,2%** em 10
  janelas de validação. Ele superou o Holt-Winters em log (5,7%) e o baseline sazonal ingênuo (5,8%).
- Previsão de jan–jun/2026: **≈ R$ 10,56 mi**, cerca de 31% acima do 1º semestre de 2025 (R$ 8,04 mi). A
  faixa aproximada de 95% é de ±10% por mês.
- *Evidência:* D › Previsão e anomalias; N › seção 9.

### Insight 7: existem picos de venda fora dos eventos cadastrados
- Foram detectados 23 dias anômalos (|z robusto| > 3,5). **13 coincidem com eventos** (Black Friday, Natal),
  o que é esperado.
- **10 não têm evento cadastrado.** Eles se concentram nas semanas antes da Black Friday (28/11/2024 e
  08, 15 e 19/11/2025) e depois do Natal (26, 27 e 31/12/2024). Esses dias são candidatos a campanhas
  dedicadas ("esquenta Black Friday", "pós-Natal") e deveriam ser registrados no calendário comercial. Os picos
  de 12 e 16/03/2025 não têm explicação aparente e devem ser investigados.
- *Evidência:* D › Previsão e anomalias; N › seção 10.

## 3.3 Recomendações gerenciais

| # | Recomendação | Base (insight) | Meta e KPI de acompanhamento | Responsável |
|---|---|---|---|---|
| R1 | **Black Friday com piso de margem.** Limitar o desconto de Eletrônicos e Informática a 15% e usar descontos maiores em categorias de alta margem (Moda, Beleza, Casa). Bloquear no sistema qualquer preço abaixo do custo. | 2 | Margem da Black Friday ≥ 15% (hoje 4,9%) e nenhum item abaixo do custo. KPI: margem bruta % no evento | Compras + Comercial |
| R2 | **Campanha de reativação do segmento "Em risco"** (1.614 clientes): cupom personalizado com validade curta, baseado na categoria que o cliente mais comprava. Não investir mídia paga em "Hibernando". | 4 | Reativar 10% do segmento em 6 meses. KPI: clientes que migram de "Em risco" para "Regulares" ou "Campeões"; taxa de recompra | Marketing/CRM |
| R3 | **Reduzir as devoluções de Moda**: tabela de medidas por produto, fotos com modelo e medidas, avaliações sobre o caimento e troca facilitada na loja física. | 3 | Devolução de Moda de 13,9% para ≤ 10% em 12 meses. KPI: taxa de devolução da categoria por canal | E-commerce |
| R4 | **Expansão no Nordeste com base em dados**: (a) estudo de viabilidade de uma loja em Fortaleza, avaliando a canibalização como ocorreu entre Recife e Salvador; (b) negociar frete regional ou centro de distribuição no NE para reduzir o frete ≈ 25% mais caro. | 1, 5 | Decisão de expansão em até 2 trimestres. KPIs: receita e crescimento por UF, frete médio por região | Diretoria + Logística |
| R5 | **Planejar estoque e caixa** do 1º semestre de 2026 com a previsão de R$ 10,6 mi (±10%), revisando todo mês com o dado real; criar campanhas para os picos sem evento (insight 7). | 6, 7 | Erro da previsão (MAPE) ≤ 10% a cada mês | Financeiro + Marketing |

**Estimativas de impacto.** São ordens de grandeza com premissas explícitas, a validar com piloto ou teste A/B:

- **R1:** em 2025 a tecnologia faturou R$ 655 mil na Black Friday, com margem de −R$ 43 mil. Com desconto de
  até 15%, a margem observada da tecnologia é de 15,4%. Mesmo que o volume caia 30%, a margem passaria a cerca
  de **+R$ 70 mil**, uma melhora de aproximadamente **R$ 110 mil** em um único evento.
- **R2:** reativar 10% do segmento (≈ 160 clientes) com 2 compras no ano ao ticket médio de R$ 906 renderia
  cerca de **R$ 290 mil** de receita.
- **R3:** levar a devolução de Moda de 13,9% para 10% preservaria cerca de **R$ 68 mil** de receita por ano,
  além do frete reverso.

## 3.4 Limitações

1. **Dados sintéticos.** Os padrões (sazonalidade, crescimento do Nordeste, prejuízo na Black Friday,
   devolução de Moda) foram **simulados de propósito** a partir de premissas do cenário. A solução demonstra
   que os métodos *encontram e quantificam* esses padrões, mas os números não descrevem uma empresa real.
2. **Preços constantes.** O gerador não aplica inflação nem reajustes, e o custo do produto é fixo nos 3 anos.
   Por isso a margem histórica pode estar distorcida.
3. **Sem custos operacionais.** A margem é **bruta** (receita − custo do produto) e não inclui frete reverso,
   marketing, comissões ou impostos. A rentabilidade real da Black Friday é ainda menor.
4. **Correlação, não causalidade.** Não dá para afirmar que limitar o desconto manteria 70% do volume. Isso
   exige um teste controlado.
5. **Segmentação.** O silhouette de 0,34 indica separação moderada, e clientes perto da fronteira podem mudar
   de grupo. O RFM ignora margem e categoria preferida.
6. **Previsão.** Com 36 meses há só 3 ciclos sazonais. A faixa de ±10% é aproximada e o erro tende a ser
   maior em novembro e dezembro.
7. **Regras de limpeza.** Itens com preço nulo receberam o preço de lista (receita possivelmente
   superestimada) e quantidades acima de 20 foram descartadas como erro (regra que precisaria ser revista para
   vendas corporativas). Os 3 produtos com custo imputado têm margem estimada.

## 3.5 Qualidade, privacidade e segurança

- **Qualidade:** 23 testes automáticos (unicidade, integridade referencial, completude, validade e
  consistência) rodam a cada execução, e o pipeline **para** se algum falhar. O relatório fica em
  `reports/relatorio_qualidade.md` e na aba *Qualidade e governança* do dashboard.
- **Rastreabilidade:** cada problema encontrado e cada tratamento aplicado ficam registrados
  (`reports/log_etl.json`).
- **Privacidade (LGPD):** dados 100% fictícios. Na camada analítica, nome, e-mail e data de nascimento são
  removidos (**princípio da minimização**); a análise usa só o ID e a faixa etária. O painel exibe apenas
  agregados.
- **Segurança em produção:** controle de acesso por perfil (gerente regional vê só sua região), banco fora de
  pastas compartilhadas, credenciais fora do código, registro de acessos e uso dos segmentos de clientes apenas
  para as finalidades informadas ao titular.
- **Uso responsável:** os segmentos servem para oferecer benefícios e comunicação relevante, não para
  discriminar preço por perfil pessoal.
