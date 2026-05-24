# FinTerminal

Terminal de análise financeira construído em Python/Streamlit.  
Analise ações B3, FIIs e ações EUA com fundamentos, health score e IA.

---

## Stack

| Camada | Tecnologia |
|--------|-----------|
| Frontend | Streamlit |
| Banco de dados | Supabase (PostgreSQL) |
| Dados fundamentalistas | Fundamentus + yfinance |
| Dados de preço | yfinance |
| IA | Google Gemini (google-genai) |
| Dados macro | FRED API + python-bcb |

---

## Configuração Supabase

### 1. Criar projeto no Supabase

1. Acesse [supabase.com](https://supabase.com) e crie um novo projeto.
2. Anote a **Project URL** e a **service_role key** (em Settings → API).

> ⚠️ Use a `service_role` key (não a `anon` key) — ela ignora RLS e é necessária
> para operações server-side. Nunca exponha essa chave no frontend.

### 2. Executar o schema inicial

No Supabase Dashboard → **SQL Editor**, cole e execute o conteúdo de:

```
database/migrations/001_initial_schema.sql
```

Isso cria todas as tabelas, índices e triggers de `updated_at`.

### 3. Configurar credenciais no Streamlit

Crie o arquivo `.streamlit/secrets.toml` (não commitado pelo `.gitignore`):

```toml
SUPABASE_URL = "https://xxxxxxxxxxxx.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."   # service_role key

[admin]
password = "sua_senha_admin_aqui"

[email]
remetente    = "seu@gmail.com"
app_password = "xxxx xxxx xxxx xxxx"
destinatario = "destino@gmail.com"

# Opcional — para dados macro via FRED
FRED_API_KEY = "sua_chave_fred"
```

### 4. Instalar dependências

```bash
pip install -r requirements.txt
```

### 5. Rodar localmente

```bash
streamlit run Home.py
```

O admin padrão é criado automaticamente no primeiro boot (username: `admin`).

---

## Mapeamento de tabelas (SQLite → Supabase)

| SQLite (legado) | Supabase (PostgreSQL) |
|-----------------|----------------------|
| `usuarios` | `users` |
| `watchlist` (itens) | `watchlist_items` |
| `portfolio_pesos` | `portfolio_positions` |
| `fundamentos_cache` | `fundamentals_cache` |
| `decisoes` | `decision_log` |
| `relatorios_enviados` | `report_history` |
| `cache_analise_ia` | `ai_analysis_cache` |
| `alertas` | `alerts` |
| `comparacoes_salvas` | `saved_comparisons` |

A interface pública de `database/db.py` é **idêntica** ao legado SQLite —
nenhuma página precisou ser alterada.

---

## Deploy no Streamlit Cloud

1. Faça push do repositório para o GitHub (o `finterminal.db` e `*.log` são ignorados).
2. Em [share.streamlit.io](https://share.streamlit.io), conecte o repositório.
3. Em **Secrets**, adicione o conteúdo do `secrets.toml` acima.
4. O Streamlit Cloud usa o `requirements.txt` automaticamente.

---

## Rollback para SQLite

O arquivo `database/db_sqlite_legacy.py` contém a implementação SQLite original.
Para reverter, substitua os imports:

```python
# de:
from database.db import ...
# para:
from database.db_sqlite_legacy import ...
```

---

## Estrutura do projeto

```
├── Home.py                         # Página principal
├── pages/
│   ├── 2_Discovery.py              # Scanner de oportunidades
│   ├── 4_Portfolio.py              # Gestão de portfólio
│   └── 6_Configuracoes.py          # Configurações e admin
├── utils/
│   ├── health_engine.py            # Motor de scoring
│   ├── scrapers.py                 # Dados fundamentalistas
│   ├── email_sender.py             # Alertas por email
│   ├── logger.py                   # Logger centralizado
│   └── tickers.py                  # Universo de ativos
├── database/
│   ├── db.py                       # Camada de dados (Supabase)
│   ├── db_sqlite_legacy.py         # Implementação SQLite (referência)
│   ├── supabase_client.py          # Client singleton
│   └── migrations/
│       └── 001_initial_schema.sql  # Schema PostgreSQL
├── logs/                           # Logs runtime (ignorados pelo git)
└── requirements.txt
```
