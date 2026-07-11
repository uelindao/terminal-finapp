# PLANO MACRO — Divergências Macro × Setoriais e seus Resultados Práticos

> Gerado em 11/07/2026. Companion do `PLANO_MESTRE.md` e `PLANO_FRONT.md` — mesmo
> protocolo (1 tarefa por sessão, âncoras por grep, pytest, commit→merge→push).
>
> **Tese do plano:** o terminal já mede DUAS coisas separadamente:
>   1. o **"deveria ser"** — regime macro, tilt setorial, inflação decomposta
>      (`macro_state.tilt_setor`, `inflation_sectoral`, `classificar_regime`);
>   2. o **"é"** — preço, força relativa, breadth (`setor_rs`, `price_history`,
>      `sector_scorecard`).
> O que ele ainda NÃO faz é **confrontá-las sistematicamente**. Divergência entre
> o que o macro prescreve e o que o preço faz é informação de primeira ordem:
> ou o mercado está atrasado (oportunidade de catch-up), ou o mercado está
> antecipando uma virada que os indicadores ainda não mostram (sinal de alerta
> para a tese macro). Este plano constrói o motor de divergências e — condição
> inegociável — o **backtest que diz o que cada divergência rendeu no passado**.
> Sinal sem resultado prático medido é opinião; aqui, nada sobe para a UI sem
> passar pelo M3 primeiro.

---

## 0. INVENTÁRIO (o que já existe e será reutilizado — verificado no código)

| Peça | Onde | Papel neste plano |
|------|------|-------------------|
| `tilt_setor(setor, macro_ctx, market)` | utils/macro_state.py:263 | O "deveria ser" por setor (±4 pts). PURO → reconstituível no passado |
| `classificar_regime(selic, vix, ipca, t10)` | utils/macro_regime.py:76 | Regime por parâmetros explícitos → reconstituível no passado |
| `pilar_macro_setorial` + inflação decomposta | utils/inflation_sectoral.py | Componente inflação do tilt; surpresa/diffusion prontos |
| `ETFS_SETORIAIS_US` + RS lines | utils/setor_rs.py | O "é" para setores US (XLK/XLF/XLE...) |
| `calcular_scorecard_setorial` | utils/sector_scorecard.py | Fundamento×técnico×macro por setor (foto atual) |
| `get_price_history_batch(tickers, dias)` | database/db.py:498 | Séries BR por setor (agregando tickers por setor canônico) |
| `macro_snapshots` (upsert por `origem`) | scripts/sync_macro.py | Persistência de séries derivadas (regime histórico, divergências) |
| `bcb.Expectativas` (Focus) | pages/3_Macro.py:425 (curva DI) | Consenso de mercado — expansível p/ IPCA/PIB/câmbio e HISTÓRICO |
| `sgs` (python-bcb) | vários | Selic 432, IPCA 433/13522, IBC-Br — histórico p/ reconstrução |
| `_buscar_yield_ntnb` | utils/health_engine.py | Juro real de mercado (p/ breakeven simplificado) |
| backtest IC/buckets | scripts/backtest_health_score.py | Molde metodológico do M3 |

**Lacuna central:** não há série temporal de RETORNO SETORIAL BR (só a foto de
momentum do price_cache) nem série de REGIME/TILT no tempo. Sem essas duas
séries não existe estudo de divergência. M0 as constrói.

---

## 1. FASE M0 — SÉRIES DE BASE E RECONSTRUÇÃO HISTÓRICA (fundação)

### M0-1 · Séries de retorno setorial BR (o "é" no tempo)
- **Arquivo novo:** `utils/setor_series.py` (+ `tests/test_setor_series.py`).
- **Tarefa:** `series_retorno_setorial(universo="BR", dias=1260) -> pd.DataFrame`
  (index=data, colunas=setor canônico): agrega `price_history` dos tickers do
  SCREENER_B3+FII por `normalizar_setor`, retorno diário **equal-weight**
  (sem market cap histórico → EW é o honesto; documentar o viés small-cap).
  US: reusar os ETFs de `setor_rs` via price_history/yfinance (são cap-weight —
  manter mercados separados, nunca comparar EW-BR com CW-US diretamente).
  Derivados: `rs_setorial(janela)` = retorno setor − retorno mediano do universo.
- **Aceite:** função pura com injeção do DataFrame de preços (testável com
  fixtures sintéticas); ≥8 setores BR com série ≥3 anos; NaN-safe (setor com
  <3 tickers ativos no dia → excluído do dia, não zerado).
- **Armadilhas:** survivorship — price_history só tem tickers ATUAIS; deixar
  explícito no docstring e no caption da UI. Feriados/gaps: usar interseção de
  datas, não reindex com ffill agressivo.

### M0-2 · Reconstrução histórica de regime e tilt (o "deveria ser" no tempo)
- **Arquivo novo:** `utils/regime_historico.py` (+ testes).
- **Tarefa:** `reconstruir_regime_tilt(anos=8) -> pd.DataFrame` (index=data
  semanal; colunas: regime_label, selic, ipca_12m, vix, t10 + tilt de CADA setor
  canônico):
  - selic diária: SGS 432 (meta) — histórico completo, grátis;
  - ipca 12m: SGS 13522;
  - vix: yfinance ^VIX (close semanal);
  - treasury 10y: yfinance ^TNX (/10).
  Para cada semana, chama `classificar_regime(...)` e `tilt_setor(...)` com os
  valores DA ÉPOCA (ambos aceitam parâmetros explícitos — por isso a reconstrução
  é fiel, não aproximada).
- **Persistência:** salvar em `macro_snapshots` com `origem="regime_tilt_hist"`
  (o upsert por origem SUBSTITUI a série — ok, pois cada rodada regenera o
  histórico completo). Recalcular no `sync_macro` semanalmente.
- **Aceite:** série semanal ≥5 anos; teste com contexto sintético confirma que o
  tilt reconstituído bate com `tilt_setor` chamado direto; spot-check manual:
  2020-03 deve classificar stress (vix>30), 2021 selic 2% deve ser juro baixo.
- **Armadilha:** o VOCABULÁRIO de setores do tilt (`_TILT_JURO_ALTO` etc.) mudou
  ao longo do tempo? Não — mas se mudar no futuro, a reconstrução usa o mapa
  ATUAL (backtest de estratégia atual sobre dados passados: correto e desejado).

### M0-3 · Snapshot prospectivo de divergências no ETL
- **Arquivo:** `scripts/sync_macro.py` (estender).
- **Tarefa:** ao final do sync diário, computar a matriz de divergência do dia
  (M2-1) e fazer **append** numa origem própria `divergencias_diarias`
  (atenção: `_salvar_snapshot_historico` SUBSTITUI por origem — para append,
  ler a série existente, concatenar o dia, dedup por data, regravar).
- **Aceite:** após 2 rodadas de ETL, a série tem 2 datas; nenhuma perda do
  histórico anterior.
- **Por quê:** a reconstrução (M0-2) cobre o passado; o snapshot diário garante
  o tracking prospectivo fiel (com os dados exatamente como estavam no dia,
  imune a revisões e mudanças de código futuras).

---

## 2. FASE M1 — MERCADO × CONSENSO (divergências de expectativa)

> O Focus (consenso de economistas) e a curva de mercado discordam o tempo todo.
> O tamanho e a direção do gap são um sinal clássico — e a API do BCB entrega o
> HISTÓRICO das expectativas por data de referência, então dá para backtestar.

### M1-1 · Focus completo no macro_cache
- **Arquivos:** `scripts/sync_macro.py`, `utils/macro_context.py`.
- **Tarefa:** via `bcb.Expectativas` (endpoint `ExpectativasMercadoAnuais` e
  `ExpectativaMercadoMensais`): IPCA 12m suavizado, Selic fim do ano corrente e
  seguinte, PIB ano, câmbio fim de ano → gravar em `macro_cache` (indicator=
  `focus_ipca_12m`, `focus_selic_eoy`, ...). TTL diário.
- **Aceite:** indicadores presentes no macro_cache após ETL; fallback silencioso
  se API cair (mantém último valor).

### M1-2 · Gap curva × Focus (juros) e breakeven × Focus (inflação)
- **Arquivo novo:** `utils/divergencia_expectativas.py` (+ testes, puro).
- **Tarefa:** duas divergências quantificadas:
  1. **Juros:** Selic implícita na curva DI para a última reunião do ano
     (`puxar_curva_di` já existe) − Focus Selic EOY → gap em pb.
     Leitura: mercado mais hawkish/dovish que economistas.
  2. **Inflação (aproximação honesta):** breakeven simplificado = expectativa
     pré 12m (curva DI interpolada) − yield real NTN-B (`_buscar_yield_ntnb`)
     → comparar com Focus IPCA 12m → gap em pp. Documentar que é proxy (sem
     ajuste de prêmio de risco/convexidade) — serve para DIREÇÃO e TENDÊNCIA
     do gap, não para nível absoluto.
- **Aceite:** funções puras com inputs injetados; testes cobrindo sinal do gap
  (hawkish/dovish/alinhado) e casos de dado ausente (retorna None, nunca 0).

### M1-3 · Card "mercado vs consenso" na página Macro
- **Arquivo:** `pages/3_Macro.py` (seção ciclo econômico ou painel global).
- **Tarefa:** faixa com os 2 gaps (pb de juros, pp de inflação), chip de direção
  (🦅 mercado mais hawkish / 🕊 mais dovish / ≈ alinhado) e caption prática:
  "gap > +50pb historicamente antecedeu revisão do Focus para cima em N de M
  episódios" (número vem do M3-3; até lá, caption qualitativa).
- **Aceite:** degrada em silêncio sem dados; segue o padrão de captions do
  terminal (todo número com "so what").

---

## 3. FASE M2 — MATRIZ DE DIVERGÊNCIA MACRO × SETOR (o coração)

### M2-1 · Motor de quadrantes ⭐
- **Arquivo novo:** `utils/divergencia_setorial.py` (+ testes, puro).
- **Tarefa:** `matriz_divergencia(tilts: dict, rs_3m: dict, *, limiar_tilt=1,
  limiar_rs=0.02) -> list[dict]`. Para cada setor com tilt E RS disponíveis:

  | | RS 3m ≥ +limiar | RS neutro | RS ≤ −limiar |
  |---|---|---|---|
  | **tilt ≥ +1** | ✅ confirmação bull | ⏳ catch-up? | 🔶 **divergência A** (macro diz sim, preço diz não) |
  | **tilt 0** | — | — | — |
  | **tilt ≤ −1** | 🔷 **divergência B** (preço desafia o macro) | ⏳ | ✅ confirmação bear |

  Cada item: `{setor, quadrante, tilt, rs_3m, magnitude (|tilt_norm − rs_norm|),
  leitura}` onde `leitura` é a interpretação padrão:
  - **divergência A** (favorecido & fraco): ou o setor está barato p/ o regime
    (candidato a reversão) ou o mercado sabe algo que o indicador não captou —
    checar micro (earnings breadth) antes de comprar a tese.
  - **divergência B** (penalizado & forte): mercado antecipando virada de regime
    — historicamente é o quadrante que antecede mudanças de fase (validar em M3).
- **Aceite:** puro, injetável, ≥10 testes (quadrantes, limiares, dados ausentes,
  magnitude ordenável).

### M2-2 · Persistência do sinal (dias em divergência)
- **Tarefa:** usar a série do M0-3 para computar `dias_em_divergencia` por
  setor/quadrante (sinal que persiste ≥2 semanas ≠ ruído de 1 dia). Função no
  mesmo módulo, alimentada pela série lida de macro_snapshots.
- **Aceite:** teste com série sintética (entra/sai/reentra no quadrante).

### M2-3 · UI: painel de divergências
- **Onde:** Discovery › rotação setorial (abaixo do scorecard — é a mesma
  audiência do drill-down F4-1) + versão compacta na Macro.
- **Tarefa:** tabela via `html_table` (padrão F0-2): setor | quadrante (chip
  colorido) | tilt | RS 3m | dias em divergência | estatística histórica (M3-2)
  | ação (🔍 ver ativos → reusa o drill-down F4-1). Ordenar por magnitude.
  Caption metodológica: EW, survivorship, limiares.
- **Aceite:** setores em divergência A/B aparecem com destaque; clique leva ao
  screener filtrado do setor.

### M2-4 · Integração "atenção hoje"
- **Arquivo:** `utils/atencao_hoje.py` (+ Home).
- **Tarefa:** novo tipo de sinal `divergencia`: setor ENTROU em divergência A/B
  (transição, não estado) → item na lista com severidade proporcional à
  magnitude. Fonte: série M0-3 (cache-first, zero rede).
- **Aceite:** testes novos no test_atencao_hoje (transição gera item; estado
  contínuo não repete).

---

## 4. FASE M3 — RESULTADOS PRÁTICOS (validação antes de acreditar) ⭐⭐

> A fase que separa este plano de um dashboard bonito. Regra: M2-3 pode até
> subir antes, mas SEM a coluna de estatística histórica o sinal é opinião.

### M3-1 · Backtest de quadrantes setoriais
- **Arquivo novo:** `scripts/backtest_divergencias.py`.
- **Tarefa:** juntar M0-1 (retornos setoriais semanais ≥5a) + M0-2 (tilt
  semanal reconstituído) → classificar cada setor-semana em quadrante →
  **forward RS** 4/13/26 semanas por quadrante:
  - média, mediana, hit rate (% de fwd RS > 0), n de episódios (episódio =
    sequência contígua no quadrante, não semana — evita contar 10x o mesmo sinal);
  - comparação com baseline (todos os setores-semana);
  - imprimir tabela + salvar JSON em `macro_cache` (indicator=
    `divergencia_stats_v1`) para a UI consumir.
- **Aceite:** roda offline com dados reais; output interpretável; teste unitário
  da função de episódios com série sintética.
- **Leitura esperada (hipóteses a validar, não verdades):** divergência A com
  persistência ≥4 semanas → catch-up positivo em 13s; divergência B →
  antecipação de mudança de regime (fwd do REGIME, não só do setor). Se o
  backtest refutar, a UI mostra o número refutado do mesmo jeito — o terminal
  não esconde resultado inconveniente (mesmo espírito do backtest FII v1).

### M3-2 · Estatística histórica na UI
- **Tarefa:** M2-3 ganha a coluna "hist.": `fwd 13s médio +X% · hit Y% · n=Z`
  lida do `divergencia_stats_v1`. Tooltip com metodologia completa.
- **Aceite:** número na tabela bate com o JSON do backtest.

### M3-3 · Backtest mercado × consenso (M1)
- **Tarefa:** a API Expectativas entrega histórico POR DATA DE REFERÊNCIA →
  série do gap curva×Focus ao longo do tempo (Focus histórico + reconstrução
  da Selic implícita é complexa; alternativa honesta: série do ERRO do Focus —
  Focus IPCA 12m vs IPCA realizado 12m depois, SGS 13522) → quando o gap/erro
  passou de X, o que Ibov/setores duration-sensíveis fizeram em 13s?
- **Aceite:** script separado ou flag no backtest_divergencias; estatística
  gravada; M1-3 ganha o número real na caption.
- **Nota de escopo:** é a perna mais exploratória — timebox de 1 sessão; se a
  qualidade do histórico do Focus decepcionar, registrar e seguir.

---

## 5. FASE M4 — ATIVIDADE × BOLSA E AMPLITUDE INTERNA

### M4-1 · Divergência atividade real × preço
- **Arquivos:** `utils/ciclo_economico.py` (estender), `pages/3_Macro.py`.
- **Tarefa:** momentum IBC-Br (3m anualizado, já no ciclo) vs retorno Ibov 3m →
  classificar: alta COM suporte de atividade (earnings-driven) vs alta SEM
  suporte (re-rating por juros/fluxo — mais frágil). Card no ciclo econômico
  com a leitura + backtest simples (fwd 13s de cada estado) no M3.
- **Aceite:** função pura testada; caption com o número histórico.

### M4-2 · Breadth setorial vs índice (amplitude interna)
- **Arquivo:** `utils/setor_series.py` (estender) + Macro/Discovery.
- **Tarefa:** % de setores BR acima da própria MM de 20 semanas vs Ibov acima
  da MM200: **topo estreito** (índice forte, amplitude fraca) e **fundo largo**
  (índice fraco, amplitude melhorando) são as divergências clássicas de
  amplitude. Série a partir do M0-1 — custo marginal baixo.
- **Aceite:** função pura testada; sinal integrado à matriz M2 como linha
  "MERCADO (amplitude)".

---

## 6. FASE M5 — INTEGRAÇÃO COM A IA E FECHAMENTO

### M5-1 · Divergências no prompt da IA
- **Arquivos:** `utils/ai_prompts.py` (build_research_prompt + prompt macro).
- **Tarefa:** bloco novo: quadrante do SETOR do ativo + estatística histórica
  ("o setor está em divergência A há 5 semanas; historicamente fwd 13s +X%,
  hit Y%") → a IA passa a citar o sinal com o resultado prático, e o tracking
  (feature já entregue) cobra a evolução na análise seguinte.
- **Aceite:** smoke test do prompt com/sem divergência.

### M5-2 · Tracking contínuo do sinal
- **Tarefa:** página Macro ganha, no fim, um expander "acompanhamento dos
  sinais": divergências abertas, idade, RS desde a abertura vs estatística
  esperada — o terminal audita a si mesmo em produção (mesma filosofia do
  diário de decisões, mas para os sinais do motor).
- **Aceite:** lê apenas de macro_snapshots/macro_cache (zero rede ao vivo).

---

## 7. ORDEM DE EXECUÇÃO RECOMENDADA

| # | Tarefa | Esforço | Depende de | Validável offline? |
|---|--------|---------|-----------|--------------------|
| 1 | M0-1 séries setoriais BR | M | — | sim (fixtures) |
| 2 | M0-2 regime/tilt histórico | M | — | sim (spot-checks) |
| 3 | M2-1 motor de quadrantes | S-M | — | sim (puro) |
| 4 | **M3-1 backtest de quadrantes** | M | 1,2,3 | sim ⭐ decide o resto |
| 5 | M0-3 snapshot diário | S | 3 | parcial (ETL) |
| 6 | M2-3 + M3-2 UI com estatística | M | 4 | não (deploy) |
| 7 | M2-2 persistência + M2-4 atenção hoje | S | 5 | sim |
| 8 | M1-1..3 mercado × consenso | M | — | parcial |
| 9 | M4-1, M4-2 atividade/amplitude | S-M | 1 | sim |
| 10 | M3-3 backtest consenso (timebox 1 sessão) | M | 8 | sim |
| 11 | M5-1, M5-2 IA + tracking | S | 6 | parcial |

**Racional da ordem:** medir (1-3) → validar (4) → só então expor (6+). Se o
backtest do passo 4 mostrar que um quadrante não tem edge, a UI nasce mostrando
isso — ou o quadrante nem sobe. É o mesmo caminho que validou o health score
(US ok, FII v1 refutado → reescrito).

---

## 8. ARMADILHAS GERAIS

- **Survivorship**: price_history cobre tickers atuais → retornos setoriais BR
  históricos têm viés otimista. Declarar em docstring, caption e no output do
  backtest. Não corrigível sem fonte paga; aceitável para RS RELATIVO entre
  setores (o viés afeta todos na mesma direção, parcialmente cancelando).
- **Equal-weight BR vs cap-weight US**: nunca misturar universos numa mesma
  estatística.
- **`_salvar_snapshot_historico` SUBSTITUI por origem** — séries prospectivas
  (M0-3) precisam de ler+concatenar+dedup antes de gravar.
- **Setor canônico**: TODA agregação via `normalizar_setor`/`LABEL_SETOR`
  (lição do F4-1: `traduzir_setor` é outro mapa e NÃO casa).
- **Episódios, não semanas**: qualquer hit rate contado por semana infla n e
  autocorrelaciona — contar por episódio contíguo.
- **APIs BCB instáveis**: tudo cache-first com fallback ao último snapshot;
  ETL tolera falha parcial (padrão já usado no sync_macro).
- **Não prometer causalidade**: toda caption usa "historicamente antecedeu /
  coincidiu", nunca "vai acontecer". n pequeno (<10 episódios) → mostrar o n
  e rebaixar a confiança na UI.
