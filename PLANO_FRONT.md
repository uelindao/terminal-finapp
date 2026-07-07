# PLANO FRONT — Evolução de Front-end, UX e UI do FinTerminal

> Gerado em 06/07/2026 após a execução do PLANO_MESTRE (Fases 0-6 essencialmente
> completas). Companion do `PLANO_MESTRE.md` — mesmo protocolo de execução
> (1 tarefa por sessão, confirmar linhas com grep, pytest, commit→merge→push com hash).
>
> **Tese do plano:** o terminal já tem um design system maduro (`utils/components.py`,
> 50+ componentes) e conteúdo analítico de nível institucional. O gap de UX não é
> falta de peças — é (a) as páginas NÃO adotam as peças que existem, (b) a
> informação não está organizada pelos MOMENTOS DE USO do analista, e (c) faltam
> os "fechos de ciclo" (ação no fim de cada tela). Este plano ataca nessa ordem.

---

## 1. PARA QUEM E PARA QUÊ (a base de toda decisão de UX)

**Persona:** analista individual (o próprio dono), decisões próprias, BR + US,
desktop em ~90% do uso, sessões curtas em mobile (conferir carteira/preço).
Não há usuário "iniciante" a proteger — densidade é FEATURE, não bug. O modelo
é Bloomberg/Koyfin: escanear, não ler.

**Jobs-to-be-done — cada página serve UM momento:**

| # | Momento | Frequência | Pergunta que a tela responde | Página | Tempo alvo |
|---|---------|-----------|------------------------------|--------|-----------|
| J1 | Ritual da manhã | diária | "o que mudou? o que exige atenção HOJE?" | Home | ≤ 3 min |
| J2 | Leitura de regime | semanal | "onde estamos no ciclo? o que favorece?" | Macro | ~10 min |
| J3 | Garimpo | semanal | "quais setores/ativos merecem olhar?" | Discovery | ~20 min |
| J4 | Deep dive | por decisão | "compro/vendo/mantenho ESTE ativo?" | Research | 15-45 min |
| J5 | Gestão | semanal/mensal | "risco, performance, IR da carteira?" | Portfolio | ~15 min |

**Regra de ouro:** toda mudança de front deve ser julgada por "reduz o tempo até
a resposta do job da página?" Se não reduz, é decoração.

---

## 2. PRINCÍPIOS DE DESIGN (decorar antes de editar UI)

1. **Resposta acima da dobra.** O job da página se responde SEM scroll. Detalhe
   e evidência vêm abaixo (progressive disclosure), nunca antes.
2. **Escaneável > legível.** Números grandes, deltas coloridos, chips de status.
   Texto corrido só em captions (1-2 linhas) e análises de IA.
3. **Todo número tem um "so what".** Já avançamos (captions em todos os gráficos).
   Manter: nenhum gráfico/tabela novo entra sem leitura interpretativa.
4. **Toda tela termina em ação.** Ver um ativo → poder abrir o deep dive.
   Ver um setor → poder rastreá-lo. Decidir → poder registrar. Sem becos sem saída.
5. **Contexto persistente.** Regime macro (cockpit) e busca global em toda página
   (feito). O usuário nunca "sai" do mercado ao navegar.
6. **Latência percebida ≈ zero.** Cache-first, lazy sections (feito), skeleton
   nos blocos de rede, `st.form` em clusters de input, toast em vez de banner.
7. **Uma peça para cada padrão.** Um componente de tabela, um de estado vazio,
   um de seletor de seção. Variação visual = bug.

---

## 3. ESTADO ATUAL (inventário honesto — 06/jul/2026)

**Já entregue nas sessões de jul/2026:**
- Lazy rendering nas 5 páginas (seções renderizam sob demanda).
- Captions interpretativas em todos os gráficos.
- Barra de contexto macro sempre-on (Research/Discovery/Portfolio + Macro).
- Busca global de ativo na sidebar de toda página → Research.
- Sidebar reordenada pelo funil (Home→Macro→Discovery→Research→Portfolio).
- Discovery abre na rotação setorial; link de handoff Macro→Discovery.
- Bloco forward-looking, DRE trimestral e proventos no Research.

**Inconsistências medidas (contagem real no código):**

| Padrão | Componente do DS | Uso real nas páginas |
|--------|------------------|----------------------|
| Tabela de dados | `html_table()` (components:2369) | **0 usos** — 19 tabelas HTML inline duplicadas |
| Estado vazio/informativo | `empty_state`/`info_box` | 14 usos vs **34 `st.info` + 31 `st.warning` crus** |
| Feedback de ação | `show_toast()` (components:1060) | **0 usos** — 22 `st.success` que empurram o layout |
| Loading | `skeleton_loader()` (components:1464) | **0 usos** — spinners bloqueantes |
| Seletor de seção | `tabs_pill()` (components:1891) | 0 usos — 5 implementações inline de segmented_control (P4-1) |

**Diagnóstico:** o design system foi construído mas a adoção parou. A dívida de
UI é sobretudo dívida de MIGRAÇÃO — baixo risco, alto retorno de consistência.

---

## 4. FASE F0 — ADOÇÃO DO DESIGN SYSTEM (fundação; fazer primeiro)

> Tarefas mecânicas e seguras. Regra geral: NÃO mudar lógica, só a casca visual.
> Cada tarefa: `python -m pytest tests/ -q` + py_compile + commit próprio.

### F0-1 · Seletor de seção único (`section_selector`)
- **Arquivos:** `utils/components.py` (novo), 5 páginas (substituição).
- **Problema:** o P4-1 criou 5 blocos inline quase idênticos de
  `segmented_control`-com-fallback (`_SECOES_MACRO`, `_SECOES_R`, `_SECOES_D`,
  `_SECOES_C`, `_SECOES_PF`). Qualquer ajuste visual exige 5 edições.
- **Tarefa:** criar `section_selector(secoes: list[str], key: str, default: str|None) -> str`
  em components.py encapsulando o padrão (segmented_control → fallback radio →
  fallback session_state). Substituir os 5 blocos por 1 chamada cada.
- **Aceite:** as 5 páginas navegam igual a antes; grep não encontra mais
  `hasattr(st, "segmented_control")` fora de components.py.
- **Armadilha:** manter as MESMAS keys de session_state (`macro_secao`,
  `research_secao`...) para não resetar a seção dos usuários com sessão aberta.

### F0-2 · Migrar as 19 tabelas inline para `html_table()`
- **Arquivos:** `pages/1_Research.py` (4), `pages/2_Discovery.py` (5),
  `pages/4_Portfolio.py` (10). Fazer POR PÁGINA (3 sessões).
- **Tarefa:** cada `<table style=...>` construída via f-string vira
  `html_table(headers=[...], rows=[...], aligns=[...])`. Células continuam
  aceitando HTML (links de ticker, spans coloridos) — a assinatura já suporta.
- **Aceite:** tabela renderiza com o mesmo conteúdo; overflow-x consistente
  (classe `.ft-table` central); py_compile ok.
- **Armadilha:** as tabelas inline têm hover-effects via `onmouseover` inline —
  verificar se `.ft-table` já tem hover; se não, adicionar UMA vez ao CSS
  central em vez de por célula.

### F0-3 · Estados informativos: `st.info/warning` → `info_box`/`empty_state`
- **Arquivos:** as 5 páginas (1-2 sessões).
- **Tarefa:** substituição criteriosa, não cega:
  - "não há dados / seção vazia" → `empty_state(icone, titulo, descricao)`.
  - avisos contextuais/analíticos → `info_box(tipo, texto, titulo)`.
  - erros reais (except) → manter `st.warning`/`st.error` (semântica de erro).
- **Aceite:** `st.info(` restante ≤ 5 por página (só casos de erro/debug).

### F0-4 · Feedback de ação: `st.success` → `show_toast`
- **Arquivos:** Home (8), Portfolio (8), Discovery (4), Research (2).
- **Problema:** `st.success` insere um banner que EMPURRA o layout e some no
  próximo rerun; para ações rápidas (adicionado à watchlist, peso salvo), o
  toast flutuante é o padrão correto e não desloca nada.
- **Tarefa:** trocar os `st.success` de AÇÕES (não os de fim de processo longo,
  ex. "tese gerada") por `show_toast(msg, "success")`. Requer
  `inject_ui_enhancements()`/`inject_keyboard_shortcuts()` na página (já presente).
- **Aceite:** adicionar ativo à watchlist não desloca a página; toast aparece.

### F0-5 · Skeleton nos blocos de rede
- **Arquivos:** `pages/3_Macro.py` (curva DI, fear&greed), `pages/1_Research.py`
  (FMP), Home (índices).
- **Tarefa:** padrão `placeholder = st.empty()` → `skeleton_loader(n)` no
  placeholder → substituir pelo conteúdo real quando os dados chegarem. Aplicar
  só nos blocos com chamada de rede >500ms na primeira carga.
- **Aceite:** primeira carga da seção mostra shimmer em vez de página "pulando".

---

## 5. FASE F1 — HOME COMO COCKPIT DO DIA (J1: "o que mudou?")

### F1-1 · Bloco "atenção hoje" no topo ⭐ (a feature de UX mais valiosa do plano)
- **Arquivos:** novo `utils/atencao_hoje.py` (lógica pura testável) +
  `Home.py` (render no topo, antes do semáforo).
- **Fontes (todas JÁ existem no banco/código):**
  1. **Scores que se moveram:** `health_score_history` — tickers da watchlist com
     |Δscore| ≥ 5 nas últimas 24-48h (query por ticker: último vs anterior).
  2. **Cruzamentos técnicos:** `price_cache` — ativos da watchlist que cruzaram
     MM200 ou RSI saiu de [35,70] (comparar rsi_14/preço vs max_52s/min_52s).
  3. **Eventos de hoje/amanhã:** `get_eventos_macro_fixos()` (Macro) + earnings
     FMP de ativos em watchlist/carteira.
  4. **Alertas de mudança:** `utils/alertas_mudanca.py` (já detecta upgrades/
     downgrades — hoje só via e-mail).
- **Render:** lista compacta de cards-linha, cada um: ícone de severidade,
  ticker/evento, delta, e **clique → Research** (padrão `ticker_nav_url` já
  existe em components:12). Máx 8 itens, ordenados por severidade. Se nada:
  "sem mudanças relevantes — mercado calmo" (empty_state discreto).
- **Aceite:** `utils/atencao_hoje.py` com `coletar_atencao_hoje(watchlist) -> list[dict]`
  puro e testado (fixtures sintéticas); Home renderiza no topo; itens clicáveis.
- **Armadilha:** TUDO cache-first (health_score_history e price_cache já estão
  no Supabase; zero yfinance ao vivo neste bloco). Cache_data ttl=900.

### F1-2 · Reordenar a Home pelo ritual da manhã
- **Ordem alvo:** 1) atenção hoje → 2) semáforo macro (compacto) → 3) watchlist
  com scores → 4) eventos da semana → 5) oportunidades → 6) e-mail/relatório
  (fim). Home hoje mistura isso.
- **Tarefa:** mover blocos (são seções independentes); nenhum novo conteúdo.
- **Aceite:** J1 se responde no primeiro terço da página.

---

## 6. FASE F2 — RESEARCH: DECISÃO ACIMA DA DOBRA (J4)

### F2-1 · Card-veredito único no topo (hero 2.0)
- **Problema:** a resposta de J4 hoje está espalhada em 4 blocos empilhados
  (hero, KPIs, card macro, forward-looking) — muito scroll antes do veredito.
- **Tarefa:** faixa única de 2 linhas logo após o hero:
  `status do score (🟢 ACUMULAÇÃO...) · score/100 · preço vs alvo consenso
  (upside %) · forward P/E vs trailing · próximo earnings (Xd) · vento macro do
  setor (±N)`. Tudo já computado na página — é REARRANJO, não feature.
  Os blocos de origem viram detalhe (podem encolher).
- **Aceite:** em 1366×768, o veredito completo aparece sem scroll.

### F2-2 · Progressive disclosure do health score
- **Tarefa:** "evolução do health score" + breakdown de barras (hoje ~2 telas de
  altura antes das seções) vão para um `st.expander("🔬 por dentro do score")`
  ou para a seção "análise & ia". A faixa-veredito (F2-1) já mostra o número.
- **Aceite:** distância do topo até o seletor de seções cai ≥ 40%.

### F2-3 · "Comparar com peers" em 1 clique
- **Tarefa:** botão no bloco de peers → seta `comp_ativos_presel = [ticker] + peers[:4]`
  + `research_modo='Comparativo (Múltiplos)'` + rerun (os session_states já
  existem e são lidos pela sidebar).
- **Aceite:** do deep dive de PETR4 ao comparativo com os peers em 1 clique.

---

## 7. FASE F3 — PORTFOLIO: GESTÃO EM GRUPOS (J5)

### F3-1 · Agrupar as 7 análises em 4 grupos
- **Problema:** o seletor de 7 opções (pós P4-1) é largo e sem hierarquia.
- **Tarefa:** dois níveis: grupo (`📊 composição` | `📐 risco` | `📈 performance`
  | `📋 gestão & ia`) e, dentro de risco (risco+stress) e gestão (diário+ir+chat),
  um sub-seletor `tabs_pill`. Mapeamento: composição=concentração;
  risco=risco,stress; performance=backtesting; gestão&ia=diário,ir,chat.
- **Aceite:** navegar até qualquer análise em ≤ 2 cliques; nenhum conteúdo perdido.

### F3-2 · Alinhamento carteira × regime no topo ⭐
- **Tarefa:** ao lado dos KPIs da carteira, um chip-resumo: "X% da carteira em
  setores favorecidos pelo regime / Y% em penalizados" usando `tilt_setor`
  (macro_state) sobre o setor de cada posição (setor já vem do
  fundamentals_cache; pesos de ativos_alocados). Clique → expander com a lista
  posição→tilt.
- **Por quê:** é O elo entre o motor macro (validado) e a carteira — hoje o
  usuário precisa cruzar mentalmente duas páginas.
- **Aceite:** função pura `alinhamento_regime(posicoes, fund_cache, macro_ctx)`
  testada; chip no topo do Portfolio.

### F3-3 · Ação rápida por posição
- **Tarefa:** na tabela de posições, link do ticker → Research (padrão
  `ticker_nav_url`) + botão "📝 registrar decisão" que pré-abre o diário com o
  ticker preenchido (session_state).

---

## 8. FASE F4 — DISCOVERY: GARIMPO COM FLUXO (J3)

### F4-1 · Drill-down setor → screener
- **Tarefa:** no scorecard de rotação setorial, cada linha ganha "🔍 ver ativos"
  que seta `screener_setor_presel = <setor_canon>` + troca a seção para o
  screener; o screener lê o preset e aplica o filtro de setor.
- **Aceite:** do setor "energia" aos ativos de energia filtrados em 1 clique.

### F4-2 · Ticker click-through em TODAS as tabelas
- **Tarefa:** auditar screener/momentum/heatmap — todo ticker renderizado vira
  link via `ticker_nav_url(ticker)` (components:12 já faz a URL; `handle_ticker_nav`
  já trata o query param). Aproveita a migração F0-2 (células aceitam HTML).
- **Aceite:** nenhum ticker "morto" (não-clicável) nas tabelas da Discovery.

### F4-3 · Presets de screener
- **Tarefa:** 4 chips acima dos filtros: `dividendos BR` (dy≥6, score≥55),
  `growth US` (crescimento≥15%, mercado US), `FIIs descontados` (p/vp≤0.95,
  liquidez≥500k), `qualidade barata` (roe≥15, p/l≤12). Clique aplica os valores
  nos widgets de filtro (session_state antes dos widgets).
- **Aceite:** 1 clique → screener rodado com o preset; filtros visíveis refletem.

---

## 9. FASE F5 — VELOCIDADE PERCEBIDA E MICROINTERAÇÕES

### F5-1 · `st.form` nos clusters de input (era P4-2 do plano-mestre)
- DCF reverso e modelo FII (Research): 4-6 widgets que hoje rerodam a página a
  cada ajuste → envolver em `st.form` com "recalcular". **Aceite:** arrastar
  slider não reroda nada.

### F5-2 · `@st.fragment` nos blocos de IA (era P4-3)
- Veredito comparativo, análise IA do Research, chat do Portfolio: gerar análise
  não deve rerodar a página inteira. **Armadilha:** fragment não pode conter
  `st.switch_page`; verificar antes.

### F5-3 · Responsividade das tabelas (mobile)
- Com F0-2 feito, é UM lugar: `.ft-table` ganha `min-width` por coluna +
  wrapper `overflow-x:auto` + fonte reduzida em `@media (max-width:700px)`.
- Cockpit macro: já flex-wrap; validar em 390px e esconder itens de menor
  prioridade via classe `.ft-ctx-opt` em telas estreitas.

---

## 10. ORDEM DE EXECUÇÃO RECOMENDADA

| # | Tarefa | Esforço | Impacto | Validável sem deploy? |
|---|--------|---------|---------|----------------------|
| 1 | F1-1 atenção hoje (Home) | M | ⭐ altíssimo | lógica sim (pura+testes); render não |
| 2 | F0-1 section_selector | S | médio | sim |
| 3 | F2-1 card-veredito Research | M | alto | parcial |
| 4 | F3-2 alinhamento carteira×regime | M | alto | lógica sim |
| 5 | F4-1 + F4-2 drill-down e links Discovery | S-M | alto | parcial |
| 6 | F0-4 toasts | S | médio | não (visual) |
| 7 | F0-2 html_table (3 sessões) | M | médio (consistência+mobile) | sim |
| 8 | F2-2, F2-3, F3-1, F3-3, F4-3 | S cada | médio | parcial |
| 9 | F0-3, F0-5, F5-1..3 | S cada | polish | parcial |

**Regra de sessão:** máx 1 tarefa M ou 2-3 S por sessão; sempre pytest + compile;
mudanças visuais pedem validação do usuário no deploy antes da próxima da mesma página.

---

## 11. ARMADILHAS GERAIS (front no Streamlit)

- `st.session_state` de widgets: setar valor de preset ANTES do widget ser
  instanciado no script (senão StreamlitAPIException).
- `st.switch_page` não funciona dentro de fragment/form — navegação via
  `ticker_nav_url` (link) nesses contextos.
- HTML inline: sanitizar texto vindo de API (`.replace('<','&lt;')`) — padrão
  já usado; manter.
- Toast exige o CSS injetado (`inject_keyboard_shortcuts` já chamado em toda página).
- NUNCA remover keys de session_state existentes em refactor de seletor
  (quebra sessões abertas).
- Emoji em labels de seção: manter EXATAMENTE iguais entre lista e `if` —
  validar por script (padrão dos commits do P4-1).
