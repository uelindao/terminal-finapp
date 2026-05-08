import sqlite3
import datetime
import json

def get_connection():
    # Conecta ao banco (cria se não existir)
    return sqlite3.connect('data/finapp.db', check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # Tabela Watchlist
    c.execute('''
        CREATE TABLE IF NOT EXISTS watchlist (
            ticker TEXT PRIMARY KEY,
            nome TEXT,
            mercado TEXT,
            notas TEXT,
            adicionado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabela Alertas
    c.execute('''
        CREATE TABLE IF NOT EXISTS alertas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            tipo TEXT,
            threshold REAL,
            ativo INTEGER DEFAULT 1,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            disparado_em TIMESTAMP
        )
    ''')
    
    # --- CORREÇÃO AUTOMÁTICA DO SCHEMA DE CACHE ---
    c.execute("PRAGMA table_info(cache_analise_ia)")
    colunas = [col[1] for col in c.fetchall()]
    if colunas and 'resposta' not in colunas:
        c.execute("DROP TABLE cache_analise_ia")

    # Tabela Cache IA
    c.execute('''
        CREATE TABLE IF NOT EXISTS cache_analise_ia (
            ticker TEXT,
            tipo TEXT,
            resposta TEXT,
            gerado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ticker, tipo)
        )
    ''')

    # Tabela de Comps Salvas
    c.execute('''
        CREATE TABLE IF NOT EXISTS comparacoes_salvas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            tickers TEXT,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Tabela Health Scores
    c.execute('''
        CREATE TABLE IF NOT EXISTS health_scores (
            ticker          TEXT NOT NULL,
            score           REAL NOT NULL,
            score_fund      REAL,
            score_tec       REAL,
            alertas_venda   TEXT,
            calculado_em    DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ticker)
        )
    ''')

    # Tabela Historico Multiplos
    c.execute('''
        CREATE TABLE IF NOT EXISTS historico_multiplos (
            ticker  TEXT NOT NULL,
            data    DATE NOT NULL,
            pl      REAL,
            pvp     REAL,
            roe     REAL,
            margem  REAL,
            dy      REAL,
            div_ebitda REAL,
            PRIMARY KEY (ticker, data)
        )
    ''')
    
    # Tabela Portfolio Pesos
    c.execute('''
        CREATE TABLE IF NOT EXISTS portfolio_pesos (
            ticker  TEXT PRIMARY KEY,
            peso    REAL NOT NULL DEFAULT 0,
            preco_medio REAL,
            quantidade  REAL,
            atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Tabela Decisões (NOVA)
    c.execute('''
        CREATE TABLE IF NOT EXISTS decisoes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker      TEXT NOT NULL,
            tipo        TEXT NOT NULL, 
            data_decisao DATE NOT NULL,
            preco_decisao REAL NOT NULL,
            quantidade  REAL,
            tese        TEXT,
            resultado   TEXT,
            registrado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

# --- WATCHLIST ---
def adicionar_ativo(ticker, nome, mercado):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO watchlist (ticker, nome, mercado) VALUES (?, ?, ?)", 
              (ticker, nome, mercado))
    conn.commit()
    conn.close()

def remover_ativo(ticker):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker,))
    c.execute("DELETE FROM alertas WHERE ticker = ?", (ticker,))
    c.execute("DELETE FROM portfolio_pesos WHERE ticker = ?", (ticker,))
    conn.commit()
    conn.close()

def listar_watchlist():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM watchlist ORDER BY adicionado_em DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def atualizar_notas(ticker, notas):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE watchlist SET notas = ? WHERE ticker = ?", (notas, ticker))
    conn.commit()
    conn.close()

# --- ALERTAS ---
def criar_alerta(ticker, tipo, threshold):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO alertas (ticker, tipo, threshold) VALUES (?, ?, ?)", 
              (ticker, tipo, threshold))
    conn.commit()
    conn.close()

def listar_alertas():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM alertas ORDER BY criado_em DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def desativar_alerta(alerta_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE alertas SET ativo = 0 WHERE id = ?", (alerta_id,))
    conn.commit()
    conn.close()

def marcar_disparado(alerta_id):
    conn = get_connection()
    c = conn.cursor()
    agora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("UPDATE alertas SET disparado_em = ?, ativo = 0 WHERE id = ?", (agora, alerta_id))
    conn.commit()
    conn.close()

# --- CACHE IA ---
def salvar_cache_ia(ticker, tipo, resposta):
    conn = get_connection()
    c = conn.cursor()
    agora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT OR REPLACE INTO cache_analise_ia (ticker, tipo, resposta, gerado_em) VALUES (?, ?, ?, ?)", 
              (ticker, tipo, resposta, agora))
    conn.commit()
    conn.close()

def get_cache_ia(ticker, tipo, max_horas=24):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT resposta, gerado_em FROM cache_analise_ia WHERE ticker = ? AND tipo = ?", (ticker, tipo))
    row = c.fetchone()
    conn.close()
    
    if row:
        gerado_em = datetime.datetime.strptime(row['gerado_em'], "%Y-%m-%d %H:%M:%S")
        agora = datetime.datetime.now()
        if (agora - gerado_em).total_seconds() <= max_horas * 3600:
            return row['resposta']
    return None

# --- POPULAR WATCHLIST INICIAL ---
def popular_watchlist_inicial():
    from utils.tickers import BR_ACOES, BR_FIIS, BRASIL_LABELS
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM watchlist")
    count = cursor.fetchone()[0]

    if count == 0:
        todos = [
            (t, BRASIL_LABELS.get(t, t).split(" — ")[-1].strip(), "B3 (Brasil)")
            for t in (BR_ACOES + BR_FIIS)
        ]
        cursor.executemany(
            "INSERT OR IGNORE INTO watchlist (ticker, nome, mercado) VALUES (?, ?, ?)",
            todos
        )
        conn.commit()
    conn.close()

# --- HEALTH SCORE ENGINE ---
def salvar_health_score(ticker, score, score_fund, score_tec, alertas_list):
    conn = get_connection()
    conn.execute('''
        REPLACE INTO health_scores
        (ticker, score, score_fund, score_tec, alertas_venda, calculado_em)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ''', (ticker, score, score_fund, score_tec, json.dumps(alertas_list)))
    conn.commit()
    conn.close()

def get_health_scores() -> list[dict]:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    rows = conn.execute('SELECT * FROM health_scores ORDER BY score ASC').fetchall()
    conn.close()
    return [dict(r) for r in rows]

def salvar_multiplos_historicos(ticker, dados: dict):
    from datetime import date
    conn = get_connection()
    conn.execute('''
        INSERT OR REPLACE INTO historico_multiplos
        (ticker, data, pl, pvp, roe, margem, dy, div_ebitda)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (ticker, date.today().isoformat(),
          dados.get('pl'), dados.get('pvp'), dados.get('roe'),
          dados.get('margem'), dados.get('dy'), dados.get('div_ebitda')))
    conn.commit()
    conn.close()

def get_historico_multiplos(ticker) -> list[dict]:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        'SELECT * FROM historico_multiplos WHERE ticker = ? ORDER BY data',
        (ticker,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# --- PORTFOLIO PESOS ---
def salvar_peso(ticker, peso, preco_medio=None, quantidade=None):
    conn = get_connection()
    conn.execute('''
        INSERT OR REPLACE INTO portfolio_pesos
        (ticker, peso, preco_medio, quantidade, atualizado_em)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
    ''', (ticker, peso, preco_medio, quantidade))
    conn.commit()
    conn.close()

def get_pesos() -> list[dict]:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    rows = conn.execute('SELECT * FROM portfolio_pesos').fetchall()
    conn.close()
    return [dict(r) for r in rows]

# --- HISTÓRICO DE DECISÕES ---
def registrar_decisao(ticker, tipo, data_decisao, preco_decisao, quantidade, tese):
    conn = get_connection()
    conn.execute('''
        INSERT INTO decisoes (ticker, tipo, data_decisao, preco_decisao, quantidade, tese)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (ticker, tipo, data_decisao, preco_decisao, quantidade, tese))
    conn.commit()
    conn.close()

def listar_decisoes(ticker=None) -> list[dict]:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    if ticker:
        rows = conn.execute('SELECT * FROM decisoes WHERE ticker = ? ORDER BY data_decisao DESC', (ticker,)).fetchall()
    else:
        rows = conn.execute('SELECT * FROM decisoes ORDER BY data_decisao DESC').fetchall()
    conn.close()
    return [dict(r) for r in rows]

def atualizar_resultado(decision_id, resultado):
    conn = get_connection()
    conn.execute('UPDATE decisoes SET resultado = ? WHERE id = ?', (resultado, decision_id))
    conn.commit()
    conn.close()