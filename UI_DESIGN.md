# Interface do FinTerminal

O FinTerminal é uma bancada pessoal de análise. A interface prioriza exploração de séries, comparações, contexto técnico e registro de hipóteses. Os controles ficam perto dos dados; informações complementares são abertas quando necessárias.

## Perfis de leitura

A aparência tem três dimensões independentes: composição, paleta e densidade. Quatro presets combinam essas dimensões, mas qualquer perfil aceita qualquer paleta. Fontes manuais sobrevivem à navegação entre páginas.

| Perfil | Composição | Gráficos |
| --- | --- | --- |
| Terminal compacto | Bancada ampla, métricas em linhas, cantos retos, fontes IBM Plex e espaçamento compacto. | Altura padrão 330 px, traços finos e grade discreta. |
| Mesa de análise | Painéis equilibrados, hierarquia moderada e espaço para cruzar contexto e preço. | Altura padrão 400 px e grade pontilhada. |
| Caderno quantitativo | Superfícies abertas, seções pautadas, títulos serifados e largura de leitura menor. | Altura padrão 450 px, sem grade. |
| Radar visual | Área ampla, números em destaque, painéis maiores e hierarquia voltada às relações visuais. | Altura padrão 480 px e linhas mais espessas. |

Alturas explícitas de estudos específicos continuam válidas. No celular, alvos de toque mantêm pelo menos 44 px mesmo com densidade compacta. Legendas mantêm opacidade integral para conservar contraste.

Configurações → Aparência permite aplicar presets, combinar composição/paleta/densidade, visualizar uma amostra real dos componentes e substituir as famílias tipográficas. O arquivo JSON exportado contém apenas a aparência e pode ser restaurado em outro navegador. A sessão e os parâmetros `theme`, `profile` e `density` conservam as preferências de leitura; fontes personalizadas podem ser conservadas pelo arquivo exportado.

## Organização e exploração

| Página | Controles e comportamento |
| --- | --- |
| Login | Linguagem pessoal e técnica, campos visíveis e entrada pelo formulário. |
| Visão geral | Atalhos locais, separação BRL/USD e watchlist em Lista, Mapa ou Comparar. |
| Análise de ativos | Cabeçalho compacto, resumo complementar recolhido, seleção de estudo no início e análise individual ou comparação. |
| Oportunidades | Resultado do screener antes dos critérios, tabela ou mapa com eixos selecionáveis, seleção de ativos e comparação; momentum com mapa/linhas/barras. |
| Cenário macro | Contexto recolhível, recortes por período, estudo do ciclo por perspectiva, calendário filtrável, overlay persistente e pares selecionáveis nas correlações. |
| Carteira | Área Posições ou Análises, composição por ativo/setor/país/moeda, estudos de risco independentes, cenários de stress e diário filtrável. |
| Configurações | Conta, listas, carteiras, alertas, IA e aparência. Backfill e administração permanecem disponíveis apenas ao administrador. |

Na watchlist, o mapa relaciona retorno e score. O modo Ativo permite inspeção por clique; Grupo permite seleção por caixa ou laço. A seleção abre uma leitura rápida e oferece acesso à análise individual. A comparação carrega históricos pelo leitor central de preços somente nessa visualização, oferece quatro períodos e alterna retorno e drawdown. Séries por data usam somente observações compartilhadas, sem preencher lacunas, e conservam a moeda original de cada ativo. O fallback de séries sem datas informa explicitamente o alinhamento por observação.

O estudo técnico permite mudar o período, candle/linha, escala, médias e volume. As médias são calculadas com o histórico anterior ao recorte. Comparações de ativos dividem matriz/retorno, scores e síntese IA. As ferramentas de IA também são escolhidas por foco, evitando executar e renderizar todos os estudos de uma vez.

Os seletores compartilhados lembram a seção após sair e voltar à página. Abrir um ticker força o escopo individual; a ação explícita de comparar mantém o escopo múltiplo e os ativos escolhidos. Ctrl+K abre a busca, Escape fecha e restaura o foco, e Alt+1 a Alt+6 navegam entre páginas.

## Precisão da apresentação

- Ausência de score no screener aparece como não calculado, sem ser confundida com uma avaliação negativa. Pontos sem valor em um dos eixos ficam fora do mapa.
- Valores consolidados e gráficos de composição da Carteira usam BRL e o câmbio atual já disponível. A base do stress por beta é identificada como custo, com conversão das posições em USD.
- Os modelos de risco existentes mantêm retornos na moeda de origem. Para carteiras mistas, a interface informa que esses estudos não incluem variação cambial e que seus valores monetários não equivalem ao patrimônio consolidado em BRL.
- Overlay macro usa datas de referência da série, que podem diferir da divulgação. Sobreposição visual e normalização não medem causalidade.
- A barra superior comunica atualizações periódicas. Notificações continuam por ativação explícita em Alertas.

## Manutenção

| Arquivo | Responsabilidade |
| --- | --- |
| `utils/appearance.py` | Perfis, densidade, presets e importação/exportação de estado validado. |
| `utils/themes.py` | Paletas, fontes, contraste e tokens efetivos da aparência. |
| `utils/interface.css` | Composição, responsividade, densidade, controles e foco visível. |
| `utils/style.py` | Aplicação dos estilos e do template dos gráficos. |
| `utils/charts.py` | Templates Plotly, eixos, guias de leitura e comportamento dos perfis. |
| `utils/components.py` | Cabeçalhos, seletores persistentes, busca, métricas, watchlist e confirmação. |
| `utils/market_explorer.py` | Mapa, inspeção de ativos e comparação interativa da watchlist. |
| `utils/portfolio_view.py` | Agrupamento por moeda na apresentação da Home. |
| `utils/auth.py` | Login e navegação lateral compartilhada. |

Use tokens de cor, fonte e espaçamento nos novos componentes. Preserve chaves dos widgets. Prefira callbacks para presets e ações que modificam widgets já existentes. Para remoções, capture o identificador do item na ação passada a `confirm_action`.

A seleção nativa de gráficos segue a [API de seleção do Streamlit](https://docs.streamlit.io/develop/api-reference/charts/st.plotly_chart). No mapa da watchlist, clique individual e seleção de grupos têm modos separados para evitar a substituição do comportamento de clique pelo controle de seleção múltipla.

## Validação desta rodada

A suíte completa passou com 217 testes. Inclui regressões de estado, navegação, aparência, importação inválida, fontes entre páginas, dados ausentes, janelas comparáveis, alinhamento por data e preenchimento dos gráficos.

A inspeção no Chromium utilizou serviços externos isolados e dados ilustrativos. Foram verificadas as seis páginas, suas seções e estudos, configurações administrativas, login, os quatro perfis em 1440 × 1000 e 390 × 844, seleção de pontos, comparação de ativos, filtro do diário e histórico financeiro com apenas dois trimestres. Não houve transbordamento horizontal nos cenários verificados. A validação local não autentica uma conta real nem confirma a disponibilidade das APIs de produção.

```sh
python -m pytest -q
python -m compileall -q Home.py pages utils
streamlit run Home.py
```

A entrada opcional `streamlit_app.py` mantém o roteamento centralizado. O ambiente publicado usa Streamlit 1.57.0, fixado em requirements.txt para reproduzir a versão validada.

## Correção de layout no Community Cloud

Tokens, marcador de perfil e interface são enviados juntos por st.html em cada renderização. Valores de segurança nas propriedades estruturais conservam alturas, margens e espaçamento mesmo quando faltam tokens. Cartões de métricas usam HTML nativo para que o espaço reservado corresponda à altura real. O padding dos gráficos fica no layout Plotly, evitando cortar legendas.

A Home mostra seis sinais prioritários em uma grade de três colunas, duas quando a área disponível diminui e uma no celular. Os demais sinais continuam acessíveis em uma seção expansível. A chave de cache inclui os tickers da watchlist, evitando compartilhar avisos entre listas diferentes.

Esta correção foi verificada nas páginas reais com uma watchlist de 21 ativos e nos quatro perfis em computador e celular. Também foi simulada a ausência dos tokens de tamanho. A alteração em requirements.txt requer reconstrução do ambiente no Cloud; o teste local não confirma a conclusão dessa publicação.

## Bancada macro

Cinco estudos com navegação que permite voltar à comparação sem recarregar universos: Transições (mapa/ritmos/evidências), Expectativas (ano/12m/juros), Rotação (janela/moeda/universo), Laboratório (pesos/patrimônio/execuções/cobertura) e Teses (formulário/versionamento/exportação). Gráficos e métricas usam os tokens do perfil de leitura. Em telas estreitas, controles e indicadores empilham e seletores quebram em linhas; tabelas mantêm rolagem local. As etiquetas de instrumentos selecionados usam `--ink-on-accent` para conservar contraste em cada paleta.

Dados ausentes aparecem como n/d; um cálculo que depende deles é suspenso. Datas de referência, de coleta e disponibilidade assumida têm significados distintos. O usuário pode inspecionar um mês histórico, mas o contexto enviado à matriz é o mês comum mais recente, claramente identificado. Estudos de preços têm janelas, moedas e fontes próprias. O diário confirma a gravação e conserva rascunho se a confirmação for interrompida.
