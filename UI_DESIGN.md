# Interface do FinTerminal

O terminal reúne uma visão diária do mercado, análise individual, descoberta de ativos, contexto macro e gestão da carteira. A interface usa os dados e modelos existentes; os componentes compartilhados organizam sua apresentação e a navegação.

## Direção visual

Carbon é o tema padrão: grafite, acento lima e cores distintas para alta, queda, atenção e informação. IBM Plex Sans dá hierarquia aos títulos, DM Sans serve à leitura e IBM Plex Mono alinha os números. As fontes têm alternativas locais quando o serviço de fontes está indisponível.

A cor de destaque identifica seleção e ação. Métricas usam números em primeiro plano e contexto abaixo. Cards têm bordas discretas e cantos pequenos. Brilhos, fundos decorativos e ícones repetidos foram reduzidos. Os temas existentes continuam disponíveis em Aparência.

## Organização das páginas

| Página | Entrada e tarefa principal |
| --- | --- |
| Login | Formulário com rótulos visíveis e orientação clara para entrar. |
| Visão geral | Mercado, atenção diária, contexto, carteira, watchlist e relatórios, com atalhos locais. |
| Análise de ativos | Identificação do ativo e seletor de seção antes dos detalhes. Pesquisa por ticker ou empresa. |
| Oportunidades | Rotação setorial, filtros quantitativos, momentum e IA. Navegação antes do contexto macro. |
| Cenário macro | Seletor de seção no início, síntese do regime e detalhamento progressivo dos indicadores. |
| Carteira | Carteira ativa, patrimônio e resultado antes da edição. Operações e importação ficam em painéis recolhidos. |
| Configurações | Conta, listas, carteiras, alertas, IA e aparência. Administração e backfill aparecem somente para administradores. |

## Comportamentos de UX

- Navegação entre páginas por links nativos do Streamlit, com nomes orientados às tarefas.
- Seções e filtros usam controles nativos. A seleção permanece após atualização, e clicar na seção atual não deixa a página sem conteúdo.
- Busca pelo formulário, com Enter, mensagem para entrada vazia e navegação direta à análise.
- Ctrl+K abre a busca de ativos e páginas; Escape fecha e devolve o foco. Alt+1 a Alt+6 navegam entre páginas.
- Filtros de P/L mínimo e máximo têm rótulos próprios. Faixas inválidas mostram orientação e bloqueiam a aplicação.
- Watchlist mostra uma linha por ativo no computador e cards identificados no celular. As ações ficam em Opções; seleção em lote é opcional.
- Remoções de listas, carteiras e usuários nas configurações exigem confirmação. O fluxo de confirmação de ativos da Home permanece.
- A permissão de notificações é solicitada pelo controle de ativação, em vez de interromper a abertura do terminal.
- O resumo da Home separa BRL e USD. Cotações incompletas são identificadas. A Carteira usa a consolidação em BRL já existente e explicita que posições e custos em USD usam o câmbio atual.
- A barra superior comunica atualizações periódicas, evitando sugerir cotação contínua em tempo real.

## Manutenção

| Arquivo | Responsabilidade |
| --- | --- |
| `utils/themes.py` | Paletas, fontes, tokens semânticos e seleção de tema. O identificador `dark` continua válido e corresponde ao Carbon. |
| `utils/interface.css` | Layout, controles, responsividade, foco visível e redução de movimentos. |
| `utils/style.py` | Aplicação dos tokens, folha de estilo e template dos gráficos. |
| `utils/components.py` | Cabeçalhos, seleção de seções, busca, watchlist, métricas e confirmação de ações. |
| `utils/auth.py` | Login e navegação lateral compartilhada; o mecanismo de sessão foi preservado. |
| `utils/portfolio_view.py` | Agrupamento de valores por moeda para apresentação na Home. |
| `tests/test_frontend.py` | Regressões de interação, contraste dos temas principais e apresentação por moeda. |

Use tokens de cor e fonte nos novos componentes. Preserve as chaves dos widgets ao alterar seus rótulos: elas mantêm seleção, parâmetros de URL e navegação. Para operações destrutivas, passe uma ação com o identificador do item capturado à função `confirm_action`.

## Validação

A suíte completa passou com 201 testes. Os testes de interface verificam persistência de seleção, filtros na URL, busca, ações por ativo, confirmação/cancelamento, login, troca de temas, escape de texto e separação das moedas. Os temas Carbon, Koyfin e Papel têm testes de contraste mínimo de 4,5:1 para suas cores principais de texto sobre fundo e superfície; isso não substitui uma auditoria completa de acessibilidade.

A revisão no Chromium utilizou dados ilustrativos e serviços externos isolados. Foram verificadas as seis páginas em 1440 × 1000 e 390 × 844, sem transbordamento horizontal, além de filtros, presets, configurações pessoais, busca, atalhos e subseções analíticas. A validação visual não autentica uma conta real nem confirma a disponibilidade das APIs de produção.

```sh
python -m pytest -q
python -m compileall -q Home.py pages utils
streamlit run Home.py
```

A entrada opcional `streamlit_app.py` mantém o roteamento centralizado e evita configurar a página novamente na Home. A dependência mínima é Streamlit 1.41.
