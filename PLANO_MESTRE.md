# PLANO MESTRE — FinTerminal

> **Documento de planejamento e execução.** Gerado em 02/07/2026 a partir de uma revisão
> completa do código (health engine, Research, Macro, módulos macro, pipeline de dados).
> Serve de guia para sessões de implementação com modelos de contexto menor (Opus 4.7/4.8).
>
> **Como usar este documento (LEIA PRIMEIRO):**
> 1. Execute **UMA tarefa por sessão** (ou 2-3 tarefas P0 pequenas). Não tente fazer uma fase inteira.
> 2. Cada tarefa lista os **arquivos que devem ser lidos** — leia SÓ eles. Não carregue
>    páginas inteiras de 3-5k linhas no contexto sem necessidade; use busca (grep) por âncoras citadas.
> 3. Linhas citadas são da revisão de jul/2026 — **confirme com grep antes de editar** (o código muda).
> 4. Após cada mudança: rode os testes indicados, depois **commit no worktree → merge na main
>    (repo principal `D:\meu_terminal_financeiro`) → push → mostrar hash** (o app de produção
>    aponta para `main` no Streamlit Cloud).
> 5. **Não refatore além do escopo da tarefa.** Não renomeie funções públicas, não mova arquivos,
>    não "melhore de passagem". O terminal tem ~47k linhas e muitos consumidores cruzados.
> 6. Testes: `python -m pytest tests/ -q` (suite completa) ou o teste específico citado na tarefa.

---

## 1. VISÃO GERAL DO PROJETO

**O que é:** terminal de análise financeira pessoal (Streamlit + Supabase) para ações B3,
FIIs e ações EUA. Funil de decisão: regime macro → rotação setorial → stockpicking → score.

**Estado atual (avaliação de jul/2026):**

| Área | Nota | Resumo |
|---|---|---|
| Arquitetura/dados | 9/10 | ETL GitHub Actions, cache-first Supabase, circuit breaker yfinance, fachada única |
| Motor macro | 8.5/10 | Consenso de 3 motores de regime, curva DI Focus, inflação decomposta (nível+momentum+difusão+surpresa), carry real | 
| Health score | 7/10 | Multi-pilar sólido, MAS: pontuação diverge entre via cache e via live; FII é motor de 2ª classe |
| Research (deep dive) | 6.5/10 | Fluxo certo (hero→score→valuation→peers→DCF reverso), MAS: aba fundamentos rasa, zero forward-looking |
| UX/performance | 6/10 | Design system consistente, MAS: páginas monolíticas, todas as tabs executam a cada rerun |

**Tese do plano:** o lado macro já é de nível institucional. O trabalho é (a) eliminar bugs
que corrompem números, (b) dar integridade ao health score (mesmo ticker = mesma nota,
independente da fonte de dados), (c) completar os dados no Supabase, (d) aprofundar o
deep dive micro, (e) destravar a performance/fluidez da UI.

---

## 2. MAPA DO PROJETO (onde cada coisa vive)

```
Home.py                     dashboard: índices, semáforo macro, watchlist, earnings, oportunidades
pages/1_Research.py         deep dive individual + comparativo (2.705 linhas)
pages/2_Discovery.py        screener, radar de momentum, heatmap setorial
pages/3_Macro.py            painel macro completo (3.970 linhas, 6 tabs)
pages/4_Portfolio.py        carteira, risco (VaR, Brinson, stress), IR
pages/5_Configuracoes.py    admin, chaves, temas

utils/health_engine.py      motor de score (FII / ações B3 / ações US) — NÚCLEO DO TERMINAL
utils/macro_state.py        estado macro CANÔNICO (consolida 3 motores + tilt_setor puro)
utils/macro_regime.py       motor antigo 6-regimes (Selic×VIX) — vocabulário livre [legado]
utils/regime_classifier.py  motor 4-fases (curva/VIX/CPI/momentum)
utils/ciclo_economico.py    motor 4-fases por leading indicators BR/US + alocação sugerida
utils/inflation_sectoral.py transmissão inflação→setor (squeeze/tailwind) + difusão/surpresa/gap
utils/sector_scorecard.py   ranking setorial composto (fundamento 45% + técnico 25% + macro 30%)
utils/macro_context.py      garante st.session_state['macro_context'] (contrato de unidades)
utils/market_data.py        FACHADA: yf_info (circuit breaker), close_series, fundamentos()
utils/scrapers.py           Fundamentus (BR) + yfinance (US) — usado no fallback do Research
utils/yf_enrichment.py      preenche campos faltantes via yfinance.info + histórico trimestral
utils/cvm_client.py         demonstrações oficiais CVM (DRE/BP/DFC desde 2010) p/ histórico BR
utils/fmp_client.py         FMP: múltiplos históricos, peers, earnings calendar, profile
utils/brapi_client.py       BRAPI (fonte primária fundamentos BR no ETL)
utils/ai_client.py          multi-provider (DeepSeek/Gemini) + streaming
utils/ai_prompts.py         prompts em blocos cache-friendly (research/discovery/portfolio)
utils/components.py         design system (metric_card, hero, topbar, kpis...) (4.224 linhas)
utils/charts.py             base_layout, cores, toggles de gráfico
utils/tickers.py            universos (SCREENER_B3, FII_TODOS, XSTOCKS_TODOS...)
utils/setores.py            taxonomia setorial CANÔNICA (normalizar_setor)

scripts/sync_br.py          ETL BR: BRAPI → enrich yf → CVM/yf trimestral → preços → scores
scripts/sync_us.py          ETL US (FMP/yfinance)
scripts/sync_macro.py       ETL macro: snapshots BCB/FRED/inflação → macro_snapshots/macro_cache
scripts/morning_brief.py    e-mail diário (GitHub Actions)
database/db.py              camada Supabase (fundamentals_cache, health_scores, price_cache...)
tests/                      pytest — inclui test_health_engine_regression (fixtures de ativos)
```

**Tabelas Supabase relevantes:** `fundamentals_cache` (dados_json com fundamentos +
historico_trimestral), `health_scores` (score + payload alertas/breakdown + data_quality_pct),
`price_cache`, `price_history`, `macro_snapshots` (payload DataFrame json por `origem`),
`macro_cache` (indicador→valor), `ai_analyses_cache`, `etl_runs`, watchlists, portfolio.

---

## 3. CONTRATOS E CONVENÇÕES (decorar antes de editar qualquer coisa)

1. **Unidades:** ROE/margem/DY/ROIC sempre em **%** no cache (24.5, não 0.245). P/L, P/VP,
   EV/EBITDA em razão pura. yfinance entrega **decimal** → sempre ×100 na fronteira.
2. **macro_context** (session_state): `selic` (% a.a.), `ipca`/`ipca_12m` = acumulado 12m
   (% a.a.) — CANÔNICO; `ipca_mensal` = print do mês; `vix`; `treasury_10y`; `label`.
   Contrato documentado em `utils/macro_context.py`.
3. **Tickers:** BR sempre com sufixo `.SA` no cache e no yfinance. `mapear_ticker_base`
   converte variantes. FII detectado por `health_engine._is_fii` (fonte da verdade — ver bug P0-2).
4. **Setores:** usar SEMPRE `utils/setores.normalizar_setor` (taxonomia canônica:
   financeiro, energia, materiais, consumo_ciclico, consumo_defensivo, saude, utilities,
   tecnologia, industria, imobiliario, comunicacao). O `macro_regime.SETOR_NORMALIZE` é legado.
5. **Acesso a mercado:** NUNCA chamar `yf.Ticker(t).info` direto — usar `market_data.yf_info`
   (circuit breaker). Séries de preço: `market_data.close_series` / `price_history.obter_ohlcv_ativo`.
6. **Cascata de fundamentos:** cache Supabase → BRAPI (BR) / FMP (US) → yfinance.info.
   Páginas leem cache-first; ETL popula.
7. **Estilo:** UI toda em letra minúscula; HTML inline com variáveis CSS (`var(--bull)` etc.);
   `st.cache_data` com TTL explícito; exceções logadas via `utils/logger.get_logger`.
8. **Motores duplicados (cache vs live) no health_engine:** cada pilar tem
   `_calc_*_do_historico` (usa `historico_trimestral` do cache, T0 vs T-4) e a versão live
   (yfinance anual). A via cache tem prioridade. Qualquer mudança de pontuação precisa ser
   aplicada NAS DUAS vias (ver P1-1).

---

## 4. FASE 0 — BUGS P0 (corrigir antes de qualquer feature)

> Todos confirmados na revisão. Tarefas pequenas e independentes — ideais para 1 sessão cada
> (ou agrupar 2-3). Depois de cada uma: `python -m pytest tests/ -q` + fluxo commit/merge/push.

### P0-1 · Proxy "BZUN" na cadeia de transmissão (dado FALSO na tela)
- **Arquivo:** `pages/3_Macro.py` — buscar `"BZUN"` (bloco `_TRANSMISSAO`, ~linha 3024).
- **Problema:** o card da Suzano usa o ticker `BZUN` como "proxy de celulose". BZUN é a
  **Baozun Inc.** (e-commerce chinês). O "EBITDA implícito" da Suzano é calculado sobre o
  preço de uma ação sem relação nenhuma.
- **Correção:** não existe ticker confiável de celulose BHKP no Yahoo. Remover o card da
  Suzano do `_TRANSMISSAO` **ou** trocar a lógica: usar o preço da própria SUZB3 como linha
  informativa sem "EBITDA implícito", com nota "celulose não tem série pública no yahoo".
  Aproveitar e **verificar `TIO=F`** (minério): rodar
  `yf.Ticker("TIO=F").history(period="5d")` num teste manual; se vazio, o item nº 1 da cesta
  de exportação some silenciosamente — nesse caso trocar por proxy VALE ou remover da cesta
  com nota, e logar warning quando um componente da cesta não retorna dados.
- **Aceite:** nenhum card exibe número derivado de ticker errado; componentes sem dado
  aparecem como "n/d" com nota, nunca com valor calculado.

### P0-2 · `is_fii` divergente no Research (bancos renderizam como FII)
- **Arquivo:** `pages/1_Research.py` linha ~637:
  `is_fii = ticker in FII_TODOS or (ticker.endswith("11.SA") and ticker not in ['TAEE11.SA','KLBN11.SA','ENGI11.SA'])`
- **Problema:** a lista de exceções local tem 3 tickers; a de `health_engine._is_fii` tem 15
  (SANB11, BPAC11, ALUP11, BOVA11...). Resultado: SANB11/BPAC11 abrem no Research com KPIs
  de FII e "modelo de P/VP justo de FII" — análise errada para um banco.
- **Correção:** apagar a lógica local e importar:
  `from utils.health_engine import _is_fii` → `is_fii = _is_fii(ticker)`.
  (Opcional melhor: mover `_is_fii` para `utils/tickers.py` como `is_fii()` público e
  importar nos dois lugares — mas só se a sessão tiver fôlego; senão import direto resolve.)
- **Aceite:** abrir SANB11.SA e BPAC11.SA no Research → renderizam como ação (P/L, ROE),
  não como FII. HGLG11.SA continua como FII.

### P0-3 · Datas do FOMC 2026 copiadas do COPOM
- **Arquivo:** `pages/3_Macro.py` — função `get_eventos_macro_fixos()` (~linha 1042).
- **Problema:** eventos "Fed — decisão de juros (FOMC)" usam exatamente as mesmas datas do
  COPOM (17/6, 29/7, 16/9, 4/11, 9/12) — copy-paste. As reuniões do FOMC em 2026 são em
  datas próprias (terminam quarta-feira; calendário oficial em federalreserve.gov).
- **Correção:** buscar na web o calendário FOMC 2026 oficial e substituir as 5 datas.
  Conferir também as datas de IPCA/CPI/Payroll listadas (IBGE/BLS publicam calendário anual).
- **Aceite:** nenhuma data de FOMC coincide com COPOM (historicamente nunca coincidem todas).

### P0-4 · Breakdown de FII mente sobre MM200; penalidade VIX nunca aplicada a FII
- **Arquivo:** `utils/health_engine.py` ~linhas 1280-1287.
- **Problema:** o breakdown grava `"Momento Técnico (MM200)": 0` fixo e DEPOIS soma
  `penalidade_tec` ao score — o breakdown nunca reflete a penalidade real. Além disso
  `penalidade_vix` é calculada para todos mas só somada no ramo de ações — para FII é
  descartada em silêncio.
- **Correção:** (a) `breakdown["Momento Técnico (MM200)"] = penalidade_tec`;
  (b) decidir sobre o VIX: recomendo somar `penalidade_vix` também para FII (beta de FII é
  baixo, então na prática raramente penaliza) e adicionar ao breakdown; se preferir não
  aplicar, deletar o cálculo para FII e comentar o porquê.
  Há também `_detectar_segmento_fii` chamado 2× (linhas ~1153 e ~1276) — reusar a variável.
- **Aceite:** para um FII abaixo da MM200, o breakdown mostra a penalidade negativa e a soma
  dos itens do breakdown bate com o score salvo. `pytest tests/test_health_engine*.py -q` verde.

### P0-5 · Parser de notícias do Research usa formato antigo do yfinance
- **Arquivo:** `pages/1_Research.py` — seção "notícias & sentimento" (~linha 2649).
- **Problema:** usa `item.get('title')`, `item.get('publisher')`,
  `item.get('providerPublishTime')`, `item.get('uuid')` — o yfinance atual aninha tudo em
  `item['content']` (a página Macro já trata isso em `renderizar_noticias`, ~linha 907).
  O `except:` engole o erro → a seção mostra "Sem notícias" para sempre.
- **Correção:** replicar o parsing de `renderizar_noticias` do 3_Macro.py (extrair
  `content`, `title`, `provider.displayName`, link aninhado). Melhor ainda: mover
  `renderizar_noticias` para `utils/components.py` e importar nas duas páginas.
- **Aceite:** abrir AAPL no Research → notícias aparecem com título/fonte/link.

### P0-6 · Heurística de unidade por magnitude corrompe DY/ROE/margem pequenos
- **Arquivos:** `scripts/sync_br.py` (`transform_brapi`, ~linhas 88-98),
  `utils/yf_enrichment.py` (`_pct`, ~linha 37), `utils/market_data.py` (`_pct`, ~linha 299).
- **Problema:** a regra "se `abs(v) < 2.0` (ou `< 1.0` p/ DY) então ×100" converte valores
  legítimos: DY real de 0.9% (já em %) vira 90%; ROE de 1.5% vira 150%; margem de 1.8% vira
  180%. Empresas de margem fina (varejo, distribuição) e pagadoras pequenas são corrompidas
  sistematicamente no cache. **Este é um dos motivos de dados "não refletirem a realidade".**
- **Correção (por fonte, não por magnitude):**
  - BRAPI: documentar/confirmar a unidade real testando 3 tickers conhecidos
    (ex.: ITUB4 ROE ~20%, TAEE11 DY ~9%, PETR4 margem ~15%) via chamada direta à API;
    fixar a conversão de acordo (provavelmente BRAPI já entrega em % — nesse caso REMOVER a
    heurística e apenas arredondar).
  - yfinance: `returnOnEquity`/`profitMargins`/`dividendYield` são SEMPRE decimais → ×100
    incondicional (sem `if abs<2`), com sanity range depois (DY>30 → None etc.).
  - Adicionar ao final de `transform_brapi` uma chamada a `scrapers.validar_fundamentos`
    (ranges realistas) — hoje o ETL BR **não valida ranges** antes de persistir.
- **Aceite:** criar `tests/test_units.py` com casos: `_pct(0.245)==24.5`, `_pct(24.5)==24.5`
  (não 2450), DY 0.9% permanece 0.9%. Rodar sync manual de 3 tickers e conferir no Supabase.

### P0-7 · Comparativo do Research: NameError com seleção vazia
- **Arquivo:** `pages/1_Research.py` — modo comparativo (~linhas 324-630).
- **Problema:** `dados_comp` só é definido dentro do `else` (quando há ativos), mas o botão
  "comparar e gerar veredito" e o bloco de health scores usam `dados_comp`/`ativos_comp`
  fora dele → com seleção vazia, clicar no botão explode (`NameError`), e
  `st.columns(len(ativos_comp))` com lista vazia levanta exceção.
- **Correção:** logo após o `if not ativos_comp:` do início, adicionar `st.stop()` depois do
  info_box (o usuário sem seleção não precisa do resto da página).
- **Aceite:** modo comparativo com 0 ativos selecionados → só o aviso, sem stack trace.

### P0-8 · Verificar campo `reuniao` da curva DI (risco de curva silenciosamente vazia)
- **Arquivo:** `pages/3_Macro.py` — `puxar_curva_di()` (~linha 387) e `_COPOM_CALENDAR` (~363).
- **Problema potencial:** o código compara `row['reuniao']` com chaves `"1/2026"`. Se a API
  do BCB retorna `"R1/2026"` (formato usado historicamente pelo endpoint
  ExpectativasMercadoSelic), NADA casa e a curva cai para o fallback anual sem avisar.
- **Correção:** rodar uma célula de teste com `bcb.Expectativas` e imprimir valores únicos
  de `reuniao`. Se vier com prefixo `R`, normalizar: `reuniao.lstrip('R')`. Aproveitar para
  logar `warning` quando `pontos < 3` (hoje o fallback é silencioso).
- **Aceite:** curva DI na aba Brasil mostra pontos por reunião COPOM (`fonte: copom`), não anual.

---

## 5. FASE 1 — INTEGRIDADE DO HEALTH SCORE

> Objetivo: **mesmo ticker → mesma nota**, independente de qual fonte de dados estava
> disponível, e score de FII comparável ao de ações. O health score é o número central do
> terminal (decide "ACUMULAÇÃO" vs "VENDA DEFINITIVA") — integridade vem antes de features.

### P1-1 · Unificar pontuação entre via cache e via live
- **Arquivos:** `utils/health_engine.py` (ler funções: `calcular_crescimento`,
  `_calc_crescimento_do_historico`, `calcular_piotroski`, `calcular_piotroski_do_historico`).
- **Problema:** a via cache penaliza queda de lucro (−3/−5 pts); a via live só alerta, sem
  penalizar. Piotroski live = anual; cache = trimestre YoY. O score muda conforme a fonte.
- **Tarefa (em 3 passos, pode ser 1 sessão cada):**
  1. Copiar a tabela de pontuação de `_calc_crescimento_do_historico` (thresholds simétricos:
     >20% +5, >5% +3, <−5% −3, <−20% −5) para dentro de `calcular_crescimento` (via live).
  2. Registrar a via usada: adicionar `breakdown["Fonte dos dados"] = "cache trimestral" | "yfinance live"`
     no `calcular_health_score` (basta setar uma flag onde escolhe entre `historico_trim` e `acao`).
  3. Piotroski: suavizar o ruído trimestral usando **TTM** quando houver ≥8 trimestres no
     cache (somar 4 trimestres vs 4 anteriores para receita/lucro/CFO; pontos de balanço
     continuam T0 vs T-4). Manter T0 vs T-4 como fallback com <8 trimestres.
- **Aceite:** `tests/test_health_engine_regression.py` atualizado (os valores esperados das
  fixtures VÃO mudar — recalcular e revisar manualmente se fazem sentido antes de fixar).

### P1-2 · Remover a extrapolação otimista do Piotroski e o F7 default=1
- **Arquivo:** `utils/health_engine.py` — ambas as funções Piotroski.
- **Problema:** `round((sum/n)*9)` com poucos critérios válidos infla o F-Score;
  F7 (diluição) default 1 sem dado é viés otimista.
- **Correção:** reportar `f_score` como `X/n_validos` sem extrapolar; na pontuação do pilar,
  usar proporção (`f_score/n_validos >= 0.78` → +10; `>= 0.55` → +5; `<= 0.22` → −6).
  F7 sem dado → None (não conta), não 1.
- **Aceite:** fixture com 5 critérios válidos e 4 hits não pontua como "quase 8/9".

### P1-3 · Cache de score: servir também scores baixos legítimos
- **Arquivo:** `utils/health_engine.py` ~linha 995 (`if idade < 86400 and h.get('score',0) > 50`).
- **Problema:** score ≤50 nunca é servido do cache (recalcula sempre — lento) porque 50 é
  também o valor de fallback de erro.
- **Correção:** o caminho de erro hoje salva `score=None` (não 50) — então o guard `>50` é
  desnecessário; trocar por `h.get('score') is not None`. Confirmar lendo o bloco de
  exceção no fim de `calcular_health_score` antes de mudar.
- **Aceite:** ticker com score 42 no banco, recalculado há <24h, retorna do cache.

### P1-4 · Valuation relativo ao próprio histórico (FMP) dentro do score
- **Arquivos:** `utils/health_engine.py` (pilar valuation, ~linha 1362) e
  `utils/fmp_client.py` (`get_multiplos_medios` — já usado no Research).
- **Ideia:** hoje o pilar de valuation usa thresholds absolutos por setor. Adicionar um
  ajuste de ±4 pts pelo percentil do múltiplo atual vs. a própria história de 5-10 anos
  (dados já existentes no Research): percentil P/L <25% → +4; <40% → +2; >75% → −2; >90% → −4.
- **Cuidados p/ modelo executor:** FMP tem rate limit no tier free — NO ETL, cachear o
  resultado em `fundamentals_cache.dados_json['multiplos_hist']` durante o sync (1×/dia),
  e o health engine lê do cache, nunca chama FMP por ticker em tempo de score.
- **Aceite:** breakdown mostra `"  ↳ Percentil P/L 10a": "32%"` e o ajuste aplicado.

### P1-5 · FII engine v2 (motor de primeira classe)
- **Arquivos:** `utils/health_engine.py` (bloco MOTOR 1), `scripts/sync_br.py` (coleta).
- **Problema:** FII tem só 2 pilares (P/VP 40 + yield 40 → máx ~80) vs. 100 das ações —
  ranking cross-asset enviesado; e ignora vacância, alavancagem, liquidez, concentração.
- **Tarefa (grande — dividir em 2-3 sessões):**
  1. **Coleta** (sessão 1): scrape da listagem do Fundamentus FII
     (`fundamentus.com.br/fii_resultado.php` — UMA request cobre todos os FIIs: P/VP,
     DY, liquidez diária, vacância média, qtd imóveis, cap rate). Persistir no
     `fundamentals_cache.dados_json` campos: `vacancia%`, `liquidez_diaria`, `cap_rate%`,
     `qtd_imoveis`. Adicionar ao `sync_br.py` como etapa própria com try/except.
  2. **Score** (sessão 2): novos pilares FII — liquidez (0-8: >R$1M/dia = 8; <R$100k = 0 com
     alerta), vacância (0-8, só tijolo: <5% = 8; >20% = −4 com alerta), consistência de
     proventos (0-4: usa o histórico de dividendos já sincronizado — desvio-padrão dos
     últimos 12 pagamentos / média; baixo desvio = 4). Rebalancear: P/VP máx 35, yield máx 35,
     novos 20, técnico ±10 → teto ~100, comparável a ações.
  3. Atualizar fixtures `tests/fixtures/fii_*.json` e o teste de regressão.
- **Aceite:** HGLG11 e MXRF11 têm score com ≥5 pilares no breakdown; teto teórico = 100.

### P1-6 · Card de impacto setorial do Research usa o motor novo
- **Arquivo:** `pages/1_Research.py` ~linha 931 (usa `macro_regime.classificar_regime` +
  `get_impacto_setor` — motor legado com matching de substring).
- **Problema:** o card pode dizer "favorável" enquanto o pilar macro-setorial do score diz
  "vento contra" (usa `macro_state.tilt_setor`) — contradição na mesma tela.
- **Correção:** trocar o card para `from utils.inflation_sectoral import pilar_macro_setorial`
  com `market = 'US' if not ticker.endswith('.SA') else 'BR'`; exibir `impacto`, `pontos` e
  `motivos` (regime + inflação). Manter o label de regime vindo de `macro_state`/cockpit.
  Atualizar também o que vai no prompt da IA (`impacto_setor_ativo` no session_state).
- **Aceite:** card e breakdown do score mostram a MESMA direção para o mesmo ticker.

---

## 6. FASE 2 — QUALIDADE E COMPLETUDE DOS DADOS (Supabase)

> Requisito do usuário: **dados que reflitam 100% a realidade, sem campos faltando**
> (há empresas sem P/L, P/VP etc. no cache). Estratégia em 4 frentes.

### P2-1 · Derivar múltiplos faltantes a partir do que JÁ existe no cache
- **Arquivos:** criar `utils/derive_multiples.py`; integrar em `scripts/sync_br.py` e
  `scripts/sync_us.py` (após o enrich, antes do upsert).
- **Insight-chave:** o `historico_trimestral` (CVM/yfinance) tem receita, lucro, gross,
  ebitda, ativos, dívida, cash, shares; o `price_cache` tem preço. Quase todo múltiplo
  faltante é DERIVÁVEL:
  - `p/l = market_cap / lucro_TTM` (soma dos 4 últimos trimestres; None se lucro_TTM ≤ 0 —
    registrar `p/l_negativo: true` para a UI mostrar "prejuízo" em vez de "n/d")
  - `p/vp = market_cap / patrimonio_liquido` (PL = ativos_totais − passivos_totais se
    disponível; CVM tem; senão pular)
  - `roe% = lucro_TTM / PL × 100`
  - `margem% = lucro_TTM / receita_TTM × 100`
  - `ev/ebitda = (market_cap + divida_total − cash) / ebitda_TTM`
  - `market_cap = preco × shares` quando faltar
- **Regra de precedência:** valor do provedor (BRAPI/FMP/Fundamentus) > derivado > yfinance.
  Marcar origem por campo em `dados_json['_field_source'] = {'p/l': 'derivado', ...}`.
- **Cuidados:** tudo com sanity ranges (`scrapers.RANGES_VALIDOS`); TTM exige ≥4 trimestres;
  bancos não têm ev/ebitda (pular). Escrever `tests/test_derive_multiples.py` com um
  histórico sintético.
- **Aceite:** rodar sync BR e medir cobertura antes/depois (ver P2-2); campos críticos de
  empresas com histórico CVM ficam ≥95% preenchidos.

### P2-2 · Painel de cobertura de dados (medir para gerenciar)
- **Arquivos:** `scripts/supabase_helper.py` (nova função), `scripts/sync_br.py`/`sync_us.py`
  (chamar no fim), `pages/5_Configuracoes.py` (exibir).
- **Tarefa:** ao final de cada sync, calcular e gravar em `etl_runs` (coluna `details` json)
  a cobertura por campo: `{'p/l': 91.2, 'p/vp': 88.0, 'roe%': ...}` por mercado (BR/US/FII).
  Na página de Configurações, uma seção "qualidade dos dados" com: tabela de cobertura por
  campo, lista dos 20 tickers com pior `data_quality_pct` e a fonte de cada um, e o estado
  do circuit breaker (`market_data.provider_health()`).
- **Aceite:** dá para responder em 10 segundos "quais tickers estão sem P/VP e por quê".

### P2-3 · FIIs: fonte dedicada (BRAPI/yfinance são fracos para FII)
- Coberto pela tarefa **P1-5 passo 1** (Fundamentus fii_resultado.php traz P/VP, DY,
  vacância, liquidez de TODOS os FIIs em 1 request). Priorizar essa fonte para FII no ETL:
  para tickers em `FII_TODOS`, o Fundamentus-FII é a fonte primária de p/vp e dy%, com
  BRAPI/yf só para preço.

### P2-4 · Validação na escrita (nenhum dado insano entra no banco)
- **Arquivos:** `scripts/supabase_helper.py` (`upsert_fundamentals`).
- **Tarefa:** aplicar `scrapers.validar_fundamentos` (ranges) SEMPRE antes do upsert —
  hoje só o caminho Fundamentus valida (o ETL BRAPI não). Adicionar log de descarte:
  `logger.warning(f"{ticker}: campo X={v} fora do range — descartado")` para auditoria.
- **Aceite:** impossível persistir DY 90% ou ROE 900% (viram None + warning no log do ETL).

### P2-5 · Cobertura do histórico trimestral
- **Contexto:** `sync_br.py` busca CVM (3 anos) e cai para yfinance. Empresas fora do
  mapeamento CVM ficam com histórico curto/vazio → health score cai para via live (ver P1-1).
- **Tarefa:** adicionar ao painel P2-2 a métrica "% de tickers com ≥8 trimestres"; para os
  faltantes, logar o motivo (sem mapeamento CVM? yfinance vazio?). Aumentar `anos=3` para
  `anos=5` no `get_historico_trimestral_cvm` do sync (o TTM do P1-1 e o Research do P3-1
  precisam de 8-12 trimestres com folga).
- **Aceite:** ≥90% do SCREENER_B3 com 8+ trimestres no cache.

---

## 7. FASE 3 — RESEARCH: PROFUNDIDADE DE DEEP DIVE

### P3-1 · Aba fundamentos de verdade (maior retorno/esforço do projeto)
- **Arquivo:** `pages/1_Research.py`, tab `tab_fund`.
- **Tarefa:** substituir o gráfico único "receita vs lucro" por um bloco construído a partir
  de `cache_d['historico_trimestral']` (SEM novas chamadas de rede):
  1. **Tabela trimestral** (8-12 tri): receita, lucro, margem bruta %, margem líquida %,
     EBITDA, CFO, dívida líquida, com coluna YoY% colorida (verde/vermelho).
  2. **4 mini-gráficos** (mesmo padrão dos `_metricas_evo` já existentes na página):
     margens (bruta+líquida juntas), CFO vs lucro (qualidade do lucro), dívida líquida e
     ND/EBITDA, receita TTM.
  3. Fallback: se `historico_trimestral` ausente, manter o gráfico atual via yfinance.
- **Cuidados:** trimestres do CVM podem ter campos None — a tabela deve renderizar "—" e as
  linhas YoY pular Nones. Reusar `_peers_table_html` como referência de estilo de tabela HTML.
- **Aceite:** PETR4, VALE3 e um small cap mostram a tabela; um ticker sem histórico não quebra.

### P3-2 · Bloco forward-looking (earnings + estimativas)
- **Arquivos:** `pages/1_Research.py` (novo bloco no topo da tab análise ou no hero),
  `utils/fmp_client.py` (`get_earnings_calendar` já existe), `utils/earnings_scraper.py`.
- **Tarefa:** card "próximo resultado": data do próximo earnings (FMP), EPS estimado,
  e forward P/E vs trailing P/E (yfinance `forwardPE` já vem no `info_dict`) com leitura
  ("mercado espera lucro {crescendo|caindo} ~X%"). Para BR sem cobertura FMP, mostrar só a
  data se disponível, senão ocultar o card (nunca "n/d" gigante).
- **Aceite:** AAPL mostra data + estimativa; ticker BR sem dado oculta o bloco sem erro.

### P3-3 · Histórico de dividendos para ações (hoje só FII tem)
- **Arquivo:** `pages/1_Research.py` — o bloco de proventos de FII (~linhas 1976-2137) já
  faz tudo; hoje está dentro de `if is_fii:`.
- **Tarefa:** extrair o bloco para uma função `_render_historico_proventos(divs, titulo)` e
  chamar também para ações quando `acao_obj.dividends` não for vazio (janela 5 anos para
  ações, com agregação anual em vez de mensal).
- **Aceite:** TAEE11 (pós P0-2, como ação) e ITSA4 mostram histórico de proventos.

### P3-4 · Consolidar duplicações internas da página
- O overlay macro da tab `tab_macro` do Research duplica a `tab_overlay` do 3_Macro —
  substituir por um link/botão "abrir no painel macro" (`st.page_link`) OU deixar como está
  se a sessão estiver no limite (baixa prioridade).
- Sidebar: `get_health_scores()` é chamado 3× na sidebar — chamar 1× e reusar.

---

## 8. FASE 4 — UX/UI E FLUIDEZ

> Diagnóstico central de performance: **`st.tabs` executa TODAS as abas em todo rerun.**
> Na página Macro, isso significa: fear&greed (5 downloads yf), correlações (16 tickers × 2y),
> ciclo (vários yf) e painel global rodam TODOS a cada clique em qualquer widget.
> O cache (TTL 1h) salva a partir da 2ª execução, mas o primeiro load é brutal e qualquer
> widget fora de cache re-dispara tudo.

### P4-1 · Lazy rendering nas tabs da página Macro (maior ganho de fluidez)
- **Arquivo:** `pages/3_Macro.py`.
- **Tarefa:** trocar `st.tabs` por um seletor persistente que renderiza SÓ a seção ativa:
  ```python
  _secao = st.segmented_control("", ["🌐 painel global", "🔄 ciclo", "📅 calendário",
      "🔭 overlay", "🧠 sentimento", "🔗 correlações"], key="macro_secao",
      default="🌐 painel global")
  if _secao == "🌐 painel global": _render_painel_global()
  elif _secao == "🔄 ciclo": _render_ciclo()
  ...
  ```
  Passo mecânico: envolver o corpo de cada `with tab_x:` numa função `_render_*()` (a
  indentação já existe; é mover o bloco). **Não mudar lógica interna.** Se
  `st.segmented_control` não existir na versão do Streamlit do requirements, usar
  `st.radio(horizontal=True)`.
- **Mesma cirurgia depois em** `pages/1_Research.py` (5 tabs) e `pages/4_Portfolio.py`.
- **Aceite:** abrir a página Macro → só o painel global carrega (medir: tempo de load cai
  de dezenas de segundos frios para ~o tempo de 1 aba); trocar de seção não recarrega as outras.

### P4-2 · `st.form` nos clusters de parâmetros (DCF, modelo FII)
- **Arquivo:** `pages/1_Research.py` — DCF reverso e P/VP justo FII.
- **Problema:** cada slider/number_input dispara rerun da página INTEIRA (com todas as tabs).
- **Tarefa:** envolver os inputs de cada modelo em `with st.form("dcf_form"): ... st.form_submit_button("recalcular")`.
  Manter os valores default vindos do cache. (Após P4-1 o custo de rerun já cai muito; o
  form elimina o restante.)
- **Aceite:** arrastar o slider de WACC não recarrega a página; só o submit recalcula.

### P4-3 · Fragments para blocos independentes
- Onde já há interatividade local (watchlist na Home usa `@st.fragment` — padrão a seguir):
  aplicar `@st.fragment` no bloco de veredito IA do comparativo, no chat/análise IA do
  Research e nos gauges de sentimento. Regra: função que renderiza + widgets internos → fragment.

### P4-4 · Navegação e microinterações
- Links de ticker no comparativo abrem NOVA ABA via query param — dentro do app, preferir
  `st.page_link`/`st.switch_page` setando `research_ticker_externo` (padrão já existente).
- Skeleton: nos blocos que dependem de rede na primeira carga (curva DI, fear&greed),
  usar `st.spinner` já existente + `st.empty()` placeholder para evitar "pulo" de layout.
- Padronizar estados vazios com `empty_state()` (alguns blocos usam `st.caption`, outros
  `st.info` — escolher `empty_state`/`info_box` do design system).
- **Números:** garantir `fmt_*` de `utils/formatters` em TODO lugar (há f-strings manuais
  espalhadas com `:,.2f` que ignoram convenção pt-BR).
- Sidebar do Research: seção "visitados recentemente" é ótima — replicar na Discovery.

### P4-5 · Dashboard "cockpit de decisão" (visão de futuro, fase posterior)
- A Home já tem semáforo + watchlist + eventos. Evolução: um bloco "o que mudou desde ontem"
  (diff de health scores >5 pts, alertas novos, eventos de hoje) no topo — dados já existem
  em `health_score_history` e `alertas_mudanca.py`. Planejar junto com P6.

---

## 9. FASE 5 — FRAGILIDADES E ROBUSTEZ (hunt de bugs latentes)

Achados da revisão que não são bugs ativos, mas quebram sob condição:

1. **`except:` nus e silenciosos** — dezenas em `1_Research.py`/`3_Macro.py` engolem até
   `KeyboardInterrupt`. Tarefa mecânica de baixo risco: trocar por `except Exception as e:`
   + `logger.debug/warning`. Fazer por arquivo, 1 sessão cada, SEM mudar lógica.
2. **`@st.cache_resource` em `carregar_dados_ativo`** (Research ~647) devolve DataFrame
   mutável compartilhado entre sessões — qualquer mutação (ex.: `df_hist.index = ...`)
   afeta outros usuários. Trocar por `@st.cache_data` para o `hist`/`info` e criar o
   `yf.Ticker` fora do cache (é barato).
3. **Mutação de df cacheado na página Macro**: `df_br['IPCA_12M'] = ...`, `df_br['Selic_Real'] = ...`
   dentro da página — `st.cache_data` retorna cópia, então funciona HOJE, mas se alguém
   trocar para `cache_resource` corrompe. Adicionar comentário-guarda ou `.copy()` explícito.
4. **Calendários hardcoded** (`_COPOM_CALENDAR`, `get_eventos_macro_fixos`) expiram
   anualmente em silêncio. Adicionar guarda: se `hoje > max(datas do calendário) - 60 dias`,
   exibir `info_box` "calendário de eventos precisa de atualização" na aba calendário.
5. **`fear_greed`**: se o download multi-ticker do yfinance falhar parcialmente, `dados['^GSPC']`
   pode lançar KeyError dentro do try (ok, capturado) mas o resultado degrada para score 50
   "NEUTRO" **sem indicação visual** de que é fallback. Padrão a adotar no terminal inteiro:
   valor de fallback SEMPRE com badge "dado indisponível" (o `data_quality_badge` já existe).
6. **Health score sidebar default 50** (Research ~180: `or 50`): score ausente e score 0
   viram 50 "manutenção". Usar `is None` e mostrar "—" quando não houver score.
7. **Chave service_role no frontend** (README): o Streamlit Cloud roda o app com a chave que
   ignora RLS. Aceitável para uso pessoal; se o terminal virar multi-usuário real, migrar
   páginas para chave anon + RLS e deixar service_role só no ETL. Registrar como decisão.
8. **`renderizar_noticias`** usa `publisher.lower()` — se `provider` vier None explode
   dentro do try (capturado, mas a seção morre). Guard: `str(publisher or '').lower()`.
9. **Teste de fumaça de produção**: criar `tests/test_smoke_pages.py` que importa cada
   página com `streamlit.testing.v1.AppTest` (se a versão suportar) ou ao menos importa os
   módulos utils críticos — pega `ImportError`/`SyntaxError` antes do deploy.
10. **yfinance como ponto único de falha de preços**: o circuit breaker cobre `.info`, mas
    `history()`/`download()` cru ainda é chamado em ~30 pontos das páginas. Migração gradual
    para `market_data.close_series`/`bulk_close_history` (que têm cache) — 1 página por sessão.

---

## 10. FASE 6 — ROADMAP FUTURO (depois das fases 0-5)

Em ordem de valor para o processo de decisão:

1. **Revisões de estimativas (earnings revisions)** — o elo macro→micro que falta.
   FMP tem `analyst-estimates`; guardar snapshot mensal por ticker em `fundamentals_cache`
   e calcular breadth por setor (% de tickers com estimativa subindo). Exibir no scorecard
   setorial como 4º pilar (fund/téc/macro/revisões).
2. **Backtest do health score** — `scripts/backfill_scores.py` já existe; medir IC
   (correlação score → retorno 3m/6m forward) por mercado e publicar na página de
   Configurações. Se o score não prediz, os pesos precisam de recalibração — medir antes de
   confiar mais nele.
3. **Journal de decisão com gatilho de invalidação** — `decision_log` existe no schema;
   UI: ao registrar compra/venda, campo obrigatório "tese" + "o que invalida"; job semanal
   (morning_brief) verifica gatilhos (ex.: "spread NTN-B < 1pp") e avisa.
4. **Fluxo estrangeiro B3 + posicionamento** (dados públicos B3; scraping semanal).
5. **Atividade BR no ciclo**: adicionar IBC-Br (SGS 24363) e confiança FGV ao
   `ciclo_economico.calcular_indicadores_ciclo_br` — hoje a perna BR usa só proxies de mercado.
6. **Thresholds de regime por percentil** — `macro_regime` usa cortes fixos (Selic>10 etc.);
   recalibrar por percentil histórico 10a (ou distância ao r* que o P/L justo já estima).
7. **Alertas proativos**: diff diário de score/regime já tem base (`alertas_mudanca.py`,
   morning brief) — expandir para push por evento (earnings amanhã de ativo em carteira;
   ativo cruzou MM200; spread de FII passou do gatilho).
8. **Modo apresentação/relatório semanal em PDF** da carteira (o `pdf_generator` já existe
   para tese individual — generalizar).

---

## 11. NOTAS PARA O MODELO EXECUTOR (armadilhas conhecidas)

- **Streamlit reruns**: todo clique reexecuta o script da página inteira de cima a baixo.
  Nunca colocar chamada de rede fora de função cacheada. `st.tabs` NÃO é lazy (ver P4-1).
- **`st.cache_data` hasheia argumentos** — listas não são hasheáveis: passar `tuple(...)`
  (o código já segue esse padrão: `tickers_tuple`).
- **yfinance**: `.info` só via `market_data.yf_info`. `history()` pode voltar MultiIndex
  mesmo p/ 1 ticker (tratar `columns.get_level_values(0)`); índices podem vir com tz
  (`tz_localize(None)` antes de comparar com Timestamps ingênuos).
- **HTML inline**: os componentes usam `st.markdown(html, unsafe_allow_html=True)` com
  f-strings — cuidado com `{` literais em CSS dentro de f-string (escapar `{{ }}`), e
  sanitizar texto vindo de API (`.replace('<','&lt;')` — padrão já usado em `_itens_info`).
- **Fixtures de regressão** (`tests/test_health_engine_regression.py`): mudanças de
  pontuação QUEBRAM o teste por design. Nunca "ajustar o teste para passar" sem validar
  manualmente que o novo score da fixture faz sentido econômico (documentar no commit).
- **Supabase**: upserts via `scripts/supabase_helper.py`; payloads de DataFrame vão como
  json em `macro_snapshots.payload`. Não criar tabela nova sem migração em
  `database/migrations/` numerada.
- **Unidades**: reler a seção 3 antes de tocar em qualquer número. A maioria dos bugs
  históricos deste projeto foi de unidade (decimal vs %).
- **Git**: trabalho no worktree, merge + push na main a partir de `D:\meu_terminal_financeiro`.
  Sempre mostrar o hash do commit e o output do push ao final.

---

## 12. ORDEM DE EXECUÇÃO SUGERIDA (resumo executivo)

| # | Tarefa | Esforço | Impacto |
|---|--------|---------|---------|
| 1 | P0-1 a P0-8 (bugs) | 1-2 sessões | dados falsos somem da tela |
| 2 | P0-6 + P2-4 (unidades + validação na escrita) | 1 sessão | cache para de ser corrompido |
| 3 | P2-1 (derivar múltiplos faltantes) | 1-2 sessões | completude ~95% dos campos críticos |
| 4 | P2-2 (painel de cobertura) | 1 sessão | visibilidade permanente da qualidade |
| 5 | P4-1 (lazy tabs Macro→Research→Portfolio) | 1 sessão/página | fluidez transformada |
| 6 | P1-1 a P1-3 (integridade do score) | 2-3 sessões | mesmo ticker = mesma nota |
| 7 | P3-1 (aba fundamentos de verdade) | 1-2 sessões | deep dive vira deep dive |
| 8 | P1-5 + P2-3 (FII v2) | 2-3 sessões | FII comparável a ações |
| 9 | P1-4 (percentil no valuation) | 1 sessão | score enxerga história |
| 10 | P3-2/P3-3, P4-2/P4-3, P5-* | 1 sessão cada | polimento contínuo |
| 11 | Fase 6 (roadmap) | — | próxima geração do terminal |
