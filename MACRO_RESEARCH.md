# Bancada de pesquisa macro

Terminal pessoal para estudar rotações de médio e longo prazo. A página **Cenário macro → Bancada de rotação** reúne Transições, Expectativas, Rotação, Laboratório e Teses. A carteira inclui **Risco → Cenários macro** e o diário de teses.

## Método e interpretação

- **Transições:** atividade dessazonalizada (IBC-Br SGS 24364 ou produção industrial INDPRO) e inflação (IPCA mensal ou CPI dessazonalizado). Ritmos de 3/6 meses são anualizados; os eixos mostram mudanças do ritmo, não nível ou previsão do PIB. Confirmação usa apenas observações mensais anteriores e consecutivas. Lacunas interrompem a confirmação. IPCA curto conserva sazonalidade. Referência econômica não é data de divulgação.
- **Expectativas:** Focus anual compara o mesmo indicador, ano e base de cálculo. IPCA 12m móvel é apresentado separadamente. Revisões usam pesquisa anterior próxima à data de comparação; ausência permanece ausente. Cada indicador mostra sua própria data. A pesquisa não é a curva DI nem preço de mercado. A proxy real brasileira usa Selic atual constante por 12m e Focus recente; TIPS DFII10 representa a taxa real longa dos EUA.
- **Rotação:** preços ajustados, moeda e extremos da janela são explícitos. USD→BRL usa `(1+r_ativo)*(1+r_câmbio)-1`. RS de classes/ETFs é razão de patrimônio contra benchmark. O snapshot setorial BR legado é diferença de retornos contra a mediana em pontos percentuais, atualmente de 3 meses. Não se misturam esses métodos. Cache desatualizado e cobertura insuficiente suspendem a comparação. Valuation, qualidade e técnico são pilares distintos; falta de dado não vira score neutro.
- **Laboratório:** pesos long-only editáveis por direção macro. Execução no fechamento do primeiro pregão mensal após disponibilidade do sinal; custos incidem sobre compras e vendas, inclusive entrada inicial. Pesos derivam entre execuções. Preços incompletos suspendem o estudo. Pelo menos 24 meses após a primeira entrada. O trecho final reservado usa os mesmos pesos fixos, sem otimização. As séries contêm revisões de hoje e atrasos são hipóteses: é uma simulação retrospectiva, não prova point-in-time ou validação fora da amostra. Não inclui impostos, capacidade ou spread variável.
- **Cenários:** choques manuais por posição e câmbio, com composição exata. Etiquetas de juros/crescimento/crédito/commodities são qualitativas e editáveis, sem betas inventados. Posições sem base válida ficam excluídas e a cobertura aparece. Preço de custo como contingência é identificado.
- **Teses:** hipótese, evidências contrárias e favoráveis, condições de entrada/invalidação, horizonte e revisão. Registro append-only em `decision_log`, tipo `tese_macro`; autoria deriva da sessão. Importar cria uma cópia sob o usuário atual. Salvar exige confirmação por leitura, com repetição idempotente. Todas as revisões são paginadas. Exportação é possível se o servidor estiver indisponível.

## Correções dos modelos anteriores

Stress não representa recuperação. “Vale” exige melhora sequencial observada. Concordância, intensidade de stress e cobertura não são probabilidades. A curva EUA usa DGS10 e DGS2 na mesma data; retorno relativo de ETFs não é curva de juros ou spread de crédito. Juro real ex post usa Fisher. A inversão simplificada de uma taxa é ilustração matemática, não valor justo ou sinal de compra. Estatísticas de divergência anteriores à metodologia v2 ficam ocultas até recálculo; a confirmação ocorre antes do retorno futuro, sem filtrar pela duração final do episódio.

O fiscal usa **saldo primário = −[NFSP primário SGS 5793](https://dadosabertos.bcb.gov.br/pt_BR/dataset/5793-nfsp-sem-desvalorizacao-cambial--pib---fluxo-acumulado-em-12-meses---resultado-primario---tota)**, com superávit positivo e déficit negativo; o nominal utiliza [SGS 5727](https://dadosabertos.bcb.gov.br/pt_BR/dataset/5727-nfsp-sem-desvalorizacao-cambial--pib---fluxo-acumulado-em-12-meses---resultado-nominal---total) (NFSP consolidado em 12 meses, %PIB). SGS 4192 é PIB em USD e foi retirado dessa interpretação. Colunas novas evitam consumir o sinal/unidade dos caches legados. Variação da dívida em seis meses requer sete referências mensais sem lacunas. O semáforo é uma heurística descritiva; dados insuficientes não indicam estabilidade e a referência visual de 60% não é limite de sustentabilidade.

## Dados e Community Cloud

O aplicativo lê snapshots e históricos preparados pelo GitHub Actions. A consulta pública de séries na bancada é uma ação explícita e conserva dados de cache quando uma fonte falha. Leituras de preços ficam limitadas aos proxies escolhidos; a interface não baixa o universo inteiro de constituintes.

O ETL grava IBC-Br, INDPRO, DFII10, Focus e proxies de classes/setores. Um push na main inicia a atualização macro e dos 26 proxies, sem recarregar os constituintes BR/EUA. No fluxo semanal/manual, o backtest de divergências depende da conclusão do histórico OHLCV. A reconciliação periódica regrava preços ajustados para refletir eventos corporativos. Fontes que falham não são contabilizadas como sucesso.

Novas observações têm referência, disponibilidade, coleta, fonte e unidade. Backfill coletado hoje não inventa vintages anteriores. A tabela dedicada `macro_observations` é opcional: sem ela, o adapter preserva versões em snapshots `vintage_*` existentes. A migração `scripts/migrations/create_macro_observations.sql` permite armazenamento dedicado e imutável. Nenhuma migração é exigida para o diário de teses.

Após o push, a atualização leve inicia automaticamente. Para recalcular também as estatísticas descritivas, execute o workflow **ETL Financeiro** no GitHub com escopo **pesquisa** (macro + proxies + backtest). **macro**, **precos** e **tudo** permitem escolher os demais escopos. A interface mostra indisponibilidade enquanto não houver histórico suficiente. A coleta SGS é isolada por série, com tempo limite, tentativas limitadas e janelas menores para históricos diários. Falhas preservam as séries válidas anteriores e ficam identificadas no diagnóstico. A normalização Focus é compartilhada com o ETL; uma pesquisa parcial conserva os demais horizontes. O breakeven T10YIE é lido do snapshot de expectativas dos EUA, com a sua própria referência e coleta.

A atualização da aplicação depende do deploy da branch configurada no Community Cloud; alterações locais não chegam ao serviço sem push.

## Fontes

- [IBC-Br do BCB, série dessazonalizada 24364](https://opendata.bcb.gov.br/pt_BR/dataset/24364-central-bank-economic-activity-index-ibc-br---seasonally-adjusted)
- [Pesquisa Focus e metodologia](https://www.bcb.gov.br/controleinflacao/expectativasmercado)
- [FRED INDPRO](https://fred.stlouisfed.org/series/INDPRO), [DFII10](https://fred.stlouisfed.org/series/DFII10), [DGS2](https://fred.stlouisfed.org/series/DGS2)
- [FRED/ALFRED: períodos e vintages](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html)
