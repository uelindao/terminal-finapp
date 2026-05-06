import sqlite3
import os

def get_connection():
    """
    Garante que a pasta 'data' existe e retorna uma conexão com o SQLite.
    row_factory = sqlite3.Row permite acessar as colunas pelo nome (ex: row['ticker']).
    """
    if not os.path.exists('data'):
        os.makedirs('data')
        
    conn = sqlite3.connect('data/finapp.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Cria o schema do banco de dados relacional caso as tabelas não existam."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Tabela da Watchlist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL UNIQUE,
            nome TEXT,
            mercado TEXT,
            notas TEXT,
            adicionado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    
    # 2. Tabela do Motor de Alertas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alertas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            tipo TEXT NOT NULL,
            threshold REAL NOT NULL,
            ativo INTEGER DEFAULT 1,
            disparado_em DATETIME,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    
    # 3. Tabela de Cache da Inteligência Artificial
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cache_analise_ia (
            ticker TEXT NOT NULL,
            tipo_analise TEXT NOT NULL,
            conteudo TEXT NOT NULL,
            gerado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ticker, tipo_analise)
        );
    ''')
    
    # 4. Tabela de Cache de Cotações
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cache_preco (
            ticker TEXT NOT NULL,
            data DATE NOT NULL,
            abertura REAL, maxima REAL, minima REAL,
            fechamento REAL, fechamento_ajustado REAL, volume INTEGER,
            PRIMARY KEY (ticker, data)
        );
    ''')
    
    # 5. Tabela de Cache de Indicadores Macro
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cache_macro (
            indicador TEXT NOT NULL,
            fonte TEXT NOT NULL,
            data DATE NOT NULL,
            valor REAL,
            PRIMARY KEY (indicador, data)
        );
    ''')
    
    # 6. Tabela de Salões de Comparação
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comparacoes_salvas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            tickers TEXT NOT NULL,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    
    conn.commit()
    conn.close()

# ==========================================
# CRUD - WATCHLIST
# ==========================================

def adicionar_ativo(ticker, nome="", mercado=""):
    conn = get_connection()
    cursor = conn.cursor()
    # INSERT OR IGNORE previne erro caso o usuário tente adicionar o mesmo ticker duas vezes
    cursor.execute('''
        INSERT OR IGNORE INTO watchlist (ticker, nome, mercado)
        VALUES (?, ?, ?)
    ''', (ticker, nome, mercado))
    conn.commit()
    conn.close()

def remover_ativo(ticker):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM watchlist WHERE ticker = ?', (ticker,))
    conn.commit()
    conn.close()

def listar_watchlist():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM watchlist ORDER BY adicionado_em DESC')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows] # Converte para lista de dicionários padrão

def atualizar_notas(ticker, notas):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE watchlist SET notas = ? WHERE ticker = ?', (notas, ticker))
    conn.commit()
    conn.close()

# ==========================================
# CRUD - ALERTAS
# ==========================================

def criar_alerta(ticker, tipo, threshold):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO alertas (ticker, tipo, threshold)
        VALUES (?, ?, ?)
    ''', (ticker, tipo, threshold))
    conn.commit()
    conn.close()

def listar_alertas(ticker=None):
    conn = get_connection()
    cursor = conn.cursor()
    if ticker:
        cursor.execute('SELECT * FROM alertas WHERE ticker = ? ORDER BY criado_em DESC', (ticker,))
    else:
        cursor.execute('SELECT * FROM alertas ORDER BY criado_em DESC')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def desativar_alerta(alerta_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE alertas SET ativo = 0 WHERE id = ?', (alerta_id,))
    conn.commit()
    conn.close()

def marcar_disparado(alerta_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE alertas SET disparado_em = CURRENT_TIMESTAMP WHERE id = ?', (alerta_id,))
    conn.commit()
    conn.close()

# ==========================================
# CACHE - INTELIGÊNCIA ARTIFICIAL
# ==========================================

def get_cache_ia(ticker, tipo_analise, max_horas=24):
    """
    Retorna o relatório da IA apenas se foi gerado nas últimas N horas.
    Isso economiza tokens caros de API.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # O motor de data/hora do SQLite faz a matemática de expiração nativamente
    cursor.execute('''
        SELECT conteudo 
        FROM cache_analise_ia 
        WHERE ticker = ? AND tipo_analise = ? 
        AND gerado_em >= datetime('now', ?)
    ''', (ticker, tipo_analise, f'-{max_horas} hours'))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return row['conteudo']
    return None

def salvar_cache_ia(ticker, tipo_analise, conteudo):
    conn = get_connection()
    cursor = conn.cursor()
    # O REPLACE atualiza a linha inteira se a chave primária composta já existir
    cursor.execute('''
        REPLACE INTO cache_analise_ia (ticker, tipo_analise, conteudo, gerado_em)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    ''', (ticker, tipo_analise, conteudo))
    conn.commit()
    conn.close()