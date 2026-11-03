# FinTerminal

Terminal pessoal de análise financeira em Python/Streamlit: macro, rotação setorial,
ações B3, FIIs e ações EUA, com health score, carteira e IA.

Roda inteiro no seu PC, sobre um único arquivo SQLite. Não depende de banco na nuvem
nem tem cota. A interface usa o tema Carbon, descrito em [UI_DESIGN.md](UI_DESIGN.md).

## Como usar

Requer Python 3.11 (`py -3.11`).

```bash
py -3.11 -m pip install -r requirements.txt
```

Crie `.streamlit/secrets.toml` (fora do git):

```toml
APP_SECRET = "texto longo e aleatorio"   # criptografa chaves de IA salvas no banco
FMP_API_KEY = "..."
FMP_API_KEY_2 = "..."
FRED_API_KEY = "..."
GEMINI_API_KEY = "..."
DEEPSEEK_API_KEY = "..."

[admin]
password = "senha do usuario admin, criado no primeiro boot"

[brapi]
token = "..."

[email]
remetente = "seu@gmail.com"
app_password = "xxxx xxxx xxxx xxxx"
destinatario = "destino@gmail.com"
```

Abra o app com dois cliques em `iniciar_terminal.bat`, ou:

```bash
py -3.11 -m streamlit run streamlit_app.py
```

O app abre direto na conta do primeiro administrador, sem tela de login. Para voltar
com ela, adicione `LOGIN_OBRIGATORIO = true` ao `secrets.toml`.

## Dados

Tudo fica em `data/finterminal_local.db`, com backups em `data/backups/` (7 últimos).
Essa é a única cópia da sua carteira e do histórico de scores. Para ter uma cópia
fora do disco, defina a variável de ambiente `FINTERMINAL_BACKUP_DIR` apontando para
uma pasta sincronizada (OneDrive, Google Drive). Não coloque o banco em si nela.

O schema está em `database/schema.sql` e é aplicado automaticamente.

### Atualização (ETL)

```bash
py -3.11 scripts/etl_local.py diario
```

| Job | Conteúdo | Agendamento |
|-----|----------|-------------|
| `diario` | macro, setores, fundamentos BR e EUA, health scores | todo dia, 07:00 |
| `macro` | Selic, VIX, câmbio, Focus, inflação | 12:00 e 18:00 |
| `semanal` | histórico OHLCV, setores, backtest de divergências | domingo, 09:00 |
| `brief` | morning brief por email | dias úteis, 08:00 |

Para registrar os horários no Agendador de Tarefas do Windows:

```bash
powershell -ExecutionPolicy Bypass -File scripts\agendar_etl.ps1
```

Horário perdido com o PC desligado roda ao ligar, um job por vez. Para remover, repita
o comando com `-Remover`. A saída de cada execução vai para `logs/etl_AAAA-MM-DD.log`, e a Home
mostra um aviso se os dados ficarem parados ou se a última coleta falhar.

### Migrar do Supabase (uma vez)

Restaure o projeto no painel do Supabase e rode:

```bash
py -3.11 scripts/importar_supabase.py
```

Login, carteiras, watchlists e diário substituem o conteúdo local. O resto é mesclado
por chave natural, sem pisar no que o ETL local já coletou. `price_history` fica de fora,
porque o ETL já o reconstruiu; use `--com-precos` para trazer as ~860 mil linhas mesmo assim.
O relatório fica em `logs/importacao_supabase.json`.

## Arquitetura

```
streamlit_app.py            navegação (Home + pages/)
pages/                      Macro, Discovery, Research, Portfolio, Configurações
utils/                      motores e telas (health_engine, macro_state, market_data...)
database/
  local_db.py               SQLite com a API fluente do Supabase (select/eq/upsert...)
  schema.sql                schema único
  db.py                     funções de acesso usadas pelo app
scripts/
  etl_local.py              orquestra os sync_*.py, log e backup
  sync_br.py, sync_us.py    fundamentos e scores
  sync_macro.py             macro e histórico versionado
  sync_price_history.py     OHLCV
```

`get_supabase()`, `utils/macro_supabase.py` e `scripts/supabase_helper.py` mantêm o nome
antigo, mas falam apenas com a base local.

## Testes

```bash
py -3.11 -m pip install -r requirements-dev.txt
py -3.11 -m pytest tests -q
```

`tests/test_local_db.py` é o contrato do adaptador SQLite. Ao adicionar uma tabela ou
um `on_conflict`, atualize `database/schema.sql`: esse teste acusa o que faltar.

## Pesquisa macro e rotação

A bancada de Cenário macro reúne transições, revisões Focus, matriz de classes/setores,
laboratório retrospectivo e diário de teses. A Carteira inclui cenários manuais de preços
e câmbio. Consulte [MACRO_RESEARCH.md](MACRO_RESEARCH.md) para hipóteses, cobertura e fontes.
