import sqlite3
import json
from datetime import datetime
import hashlib

db_name = "finterminal.db"

def get_connection():
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
    return conn

def get_user_id() -> int:
    """Retorna o user_id da sessão atual ou 1 (admin) como fallback."""
    try:
        import streamlit as st
        return st.session_state.get('user_id', 1)
    except:
        return 1

# ==========================================
# AUTENTICAÇÃO E GESTÃO DE UTILIZADORES
# ==========================================

def _hash_senha(senha: str, salt: str = "finterminal_2025") -> str:
    return hashlib.sha256(f"{salt}{senha}".encode()).hexdigest()

def criar_usuario(username: str, senha: str, nome: str = "", email: str = "", is_admin: bool = False) -> bool:
    conn = get_connection()
    try:
        conn.execute('''
            INSERT INTO usuarios (username, senha_hash, nome, email, is_admin)
            VALUES (?, ?, ?, ?, ?)
        ''', (username.lower().strip(), _hash_senha(senha), nome, email, 1 if is_admin else 0))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()

def autenticar_usuario(username: str, senha: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute('''
            SELECT id, username, nome, email, is_admin
            FROM usuarios
            WHERE username = ? AND senha_hash = ?
        ''', (username.lower().strip(), _hash_senha(senha))).fetchone()

        if row:
            conn.execute('UPDATE usuarios SET ultimo_login = CURRENT_TIMESTAMP WHERE id = ?', (row['id'],))
            conn.commit()
            return dict(row)
        return None
    finally:
        conn.close()

def listar_usuarios() -> list[dict]:
    conn = get_connection()
    rows = conn.execute('SELECT id, username, nome, email, is_admin, criado_em, ultimo_login FROM usuarios ORDER BY criado_em').fetchall()
    conn.close()
    return [dict(r) for r in rows]

def alterar_senha(user_id: int, nova_senha: str) -> None:
    conn = get_connection()
    conn.execute('UPDATE usuarios SET senha_hash = ? WHERE id = ?', (_hash_senha(nova_senha), user_id))
    conn.commit()
    conn.close()

def deletar_usuario(user_id: int) -> None:
    conn = get_connection()
    tabelas = ['watchlist', 'alertas', 'portfolio_pesos', 'decisoes', 'comparacoes_salvas', 'config_solana', 'custom_mints', 'watchlists']
    for tabela in tabelas:
        try:
            conn.execute(f'DELETE FROM {tabela} WHERE user_id = ?', (user_id,))
        except:
            pass
    conn.execute('DELETE FROM usuarios WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()

def _criar_admin_padrao():
    conn = get_connection()
    count = conn.execute('SELECT COUNT(*) FROM usuarios WHERE is_admin=1').fetchone()[0]
    if count == 0:
        try:
            import streamlit as st
            senha_padrao = st.secrets.get('admin', {}).get('password', 'admin123')
        except:
            senha_padrao = 'admin123'
            
        conn.execute('''
            INSERT INTO usuarios (username, senha_hash, nome, is_admin)
            VALUES ('admin', ?, 'administrador', 1)
        ''', (_hash_senha(senha_padrao),))
        conn.commit()
    conn.close()

# ==========================================
# INICIALIZAÇÃO DA BASE DE DADOS E MIGRAÇÕES
# ==========================================

def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL,
            nome TEXT,
            email TEXT,
            is_admin INTEGER DEFAULT 0,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            ultimo_login DATETIME
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS watchlists (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL DEFAULT 1,
            nome        TEXT NOT NULL,
            descricao   TEXT DEFAULT '',
            cor         TEXT DEFAULT '#FF9900',
            icone       TEXT DEFAULT '⭐',
            padrao      INTEGER DEFAULT 0,
            criado_em   DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS watchlist (
            ticker TEXT, 
            nome TEXT, 
            mercado TEXT, 
            adicionado_em DATETIME DEFAULT CURRENT_TIMESTAMP, 
            notas TEXT, 
            user_id INTEGER DEFAULT 1, 
            watchlist_id INTEGER,
            PRIMARY KEY (ticker, user_id, watchlist_id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS fundamentos_cache (
            ticker TEXT PRIMARY KEY,
            dados_json TEXT,
            atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('CREATE TABLE IF NOT EXISTS portfolio_pesos (ticker TEXT, peso REAL, preco_medio REAL, quantidade REAL, atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP, user_id INTEGER DEFAULT 1, PRIMARY KEY (ticker, user_id))')
    c.execute('CREATE TABLE IF NOT EXISTS health_scores (ticker TEXT PRIMARY KEY, score REAL, alertas_venda TEXT, atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS alertas (id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, tipo TEXT, threshold REAL, criado_em DATETIME DEFAULT CURRENT_TIMESTAMP, user_id INTEGER DEFAULT 1)')
    c.execute('CREATE TABLE IF NOT EXISTS decisoes (id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, tipo TEXT, data_decisao TEXT, preco_decisao REAL, quantidade REAL, tese TEXT, resultado TEXT, data_resultado TEXT, user_id INTEGER DEFAULT 1)')
    c.execute('CREATE TABLE IF NOT EXISTS cache_analise_ia (id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, tipo TEXT, conteudo TEXT, gerado_em DATETIME DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS comparacoes_salvas (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, tickers TEXT NOT NULL, criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP, user_id INTEGER DEFAULT 1)')

    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(watchlist)")
    cols = cursor.fetchall()
    pk_count = sum(1 for col in cols if col[5] > 0)
    
    if pk_count < 3:
        c.execute('CREATE TABLE IF NOT EXISTS watchlist_new (ticker TEXT, nome TEXT, mercado TEXT, adicionado_em DATETIME DEFAULT CURRENT_TIMESTAMP, notas TEXT, user_id INTEGER DEFAULT 1, watchlist_id INTEGER, PRIMARY KEY (ticker, user_id, watchlist_id))')
        c.execute('INSERT OR IGNORE INTO watchlist_new SELECT * FROM watchlist')
        c.execute('DROP TABLE watchlist')
        c.execute('ALTER TABLE watchlist_new RENAME TO watchlist')

    conn.commit()
    conn.close()
    
    _criar_admin_padrao()
    _migrar_watchlist_para_default()

def _migrar_watchlist_para_default():
    conn = get_connection()
    users = conn.execute('SELECT DISTINCT user_id FROM watchlist WHERE watchlist_id IS NULL').fetchall()

    for row in users:
        uid = row['user_id']
        wl = conn.execute('SELECT id FROM watchlists WHERE user_id=? LIMIT 1', (uid,)).fetchone()

        if not wl:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO watchlists (user_id, nome, icone, cor, padrao) VALUES (?, 'principal', '⭐', '#FF9900', 1)", (uid,))
            wl_id = cursor.lastrowid
        else:
            wl_id = wl['id']

        conn.execute('UPDATE watchlist SET watchlist_id=? WHERE user_id=? AND watchlist_id IS NULL', (wl_id, uid))

    conn.commit()
    conn.close()

# ==========================================
# CACHE DE FUNDAMENTOS
# ==========================================

def salvar_fundamento_cache(ticker: str, dados: dict):
    conn = get_connection()
    conn.execute('''
        INSERT OR REPLACE INTO fundamentos_cache (ticker, dados_json, atualizado_em)
        VALUES (?, ?, CURRENT_TIMESTAMP)
    ''', (ticker, json.dumps(dados)))
    conn.commit()
    conn.close()

def get_todos_fundamentos_cache() -> dict:
    conn = get_connection()
    rows = conn.execute('SELECT ticker, dados_json FROM fundamentos_cache').fetchall()
    conn.close()
    return {r['ticker']: json.loads(r['dados_json']) for r in rows}

# ==========================================
# GESTÃO DE WATCHLISTS (COLEÇÕES)
# ==========================================

def criar_watchlist(nome: str, descricao: str = "", cor: str = "#FF9900", icone: str = "⭐") -> int:
    user_id = get_user_id()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO watchlists (user_id, nome, descricao, cor, icone)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, nome, descricao, cor, icone))
    novo_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return novo_id

def listar_watchlists() -> list[dict]:
    user_id = get_user_id()
    conn = get_connection()
    rows = conn.execute('''
        SELECT w.*, COUNT(i.ticker) as total_ativos
        FROM watchlists w
        LEFT JOIN watchlist i ON i.watchlist_id = w.id AND i.user_id = w.user_id
        WHERE w.user_id = ?
        GROUP BY w.id
        ORDER BY w.padrao DESC, w.criado_em ASC
    ''', (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def renomear_watchlist(watchlist_id: int, novo_nome: str, nova_descricao: str = "", novo_icone: str = "⭐", nova_cor: str = "#FF9900") -> None:
    conn = get_connection()
    conn.execute('''
        UPDATE watchlists
        SET nome=?, descricao=?, icone=?, cor=?
        WHERE id=? AND user_id=?
    ''', (novo_nome, nova_descricao, novo_icone, nova_cor, watchlist_id, get_user_id()))
    conn.commit()
    conn.close()

def deletar_watchlist(watchlist_id: int) -> None:
    conn = get_connection()
    user_id = get_user_id()
    conn.execute('DELETE FROM watchlist WHERE watchlist_id=? AND user_id=?', (watchlist_id, user_id))
    conn.execute('DELETE FROM watchlists WHERE id=? AND user_id=?', (watchlist_id, user_id))
    conn.commit()
    conn.close()

def get_watchlist_padrao() -> int:
    user_id = get_user_id()
    conn = get_connection()
    row = conn.execute('SELECT id FROM watchlists WHERE user_id=? ORDER BY padrao DESC, criado_em ASC LIMIT 1', (user_id,)).fetchone()

    if row:
        conn.close()
        return row['id']

    cursor = conn.cursor()
    cursor.execute("INSERT INTO watchlists (user_id, nome, icone, cor, padrao) VALUES (?, 'principal', '⭐', '#FF9900', 1)", (user_id,))
    novo_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return novo_id

def definir_watchlist_padrao(watchlist_id: int) -> None:
    user_id = get_user_id()
    conn = get_connection()
    conn.execute('UPDATE watchlists SET padrao=0 WHERE user_id=?', (user_id,))
    conn.execute('UPDATE watchlists SET padrao=1 WHERE id=? AND user_id=?', (watchlist_id, user_id))
    conn.commit()
    conn.close()

# ==========================================
# ATIVOS (CRUD NA WATCHLIST)
# ==========================================

def adicionar_ativo(ticker: str, nome: str = "", mercado: str = "", watchlist_id: int = None) -> None:
    user_id = get_user_id()
    if watchlist_id is None:
        watchlist_id = get_watchlist_padrao()
        
    conn = get_connection()
    conn.execute('''
        INSERT OR IGNORE INTO watchlist (ticker, nome, mercado, user_id, watchlist_id)
        VALUES (?, ?, ?, ?, ?)
    ''', (ticker, nome, mercado, user_id, watchlist_id))
    conn.commit()
    conn.close()

def remover_ativo(ticker: str, watchlist_id: int = None) -> None:
    user_id = get_user_id()
    conn = get_connection()
    if watchlist_id:
        conn.execute('DELETE FROM watchlist WHERE ticker=? AND user_id=? AND watchlist_id=?', (ticker, user_id, watchlist_id))
    else:
        conn.execute('DELETE FROM watchlist WHERE ticker=? AND user_id=?', (ticker, user_id))
    conn.commit()
    conn.close()

def listar_watchlist(watchlist_id: int = None) -> list[dict]:
    user_id = get_user_id()
    conn = get_connection()
    if watchlist_id is not None:
        rows = conn.execute('SELECT * FROM watchlist WHERE user_id=? AND watchlist_id=? ORDER BY adicionado_em DESC', (user_id, watchlist_id)).fetchall()
    else:
        rows = conn.execute('SELECT * FROM watchlist WHERE user_id=? ORDER BY adicionado_em DESC', (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def atualizar_notas(ticker, notas, watchlist_id):
    user_id = get_user_id()
    conn = get_connection()
    conn.execute('UPDATE watchlist SET notas=? WHERE ticker=? AND user_id=? AND watchlist_id=?', (notas, ticker, user_id, watchlist_id))
    conn.commit()
    conn.close()

def popular_watchlist_inicial():
    user_id = get_user_id()
    conn = get_connection()
    count = conn.execute('SELECT COUNT(*) FROM watchlist WHERE user_id=?', (user_id,)).fetchone()[0]
    if count == 0:
        wl_id = get_watchlist_padrao()
        ativos = [('PETR4.SA', 'petrobras', 'brasil'), ('ITUB4.SA', 'itaú unibanco', 'brasil'), ('AAPL', 'apple inc.', 'eua')]
        for t, n, m in ativos:
            conn.execute('INSERT INTO watchlist (ticker, nome, mercado, user_id, watchlist_id) VALUES (?,?,?,?,?)', (t, n, m, user_id, wl_id))
        conn.commit()
    conn.close()

# ==========================================
# PORTFÓLIO E DECISÕES
# ==========================================

def salvar_peso(ticker, peso, preco_medio=None, quantidade=None):
    user_id = get_user_id()
    conn = get_connection()
    conn.execute('''
        INSERT OR REPLACE INTO portfolio_pesos (ticker, peso, preco_medio, quantidade, user_id)
        VALUES (?,?,?,?,?)
    ''', (ticker, peso, preco_medio, quantidade, user_id))
    conn.commit()
    conn.close()

def get_pesos():
    user_id = get_user_id()
    conn = get_connection()
    rows = conn.execute('SELECT * FROM portfolio_pesos WHERE user_id=?', (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def registrar_decisao(ticker, tipo, data, preco, quantidade, tese):
    user_id = get_user_id()
    conn = get_connection()
    conn.execute('''
        INSERT INTO decisoes (ticker, tipo, data_decisao, preco_decisao, quantidade, tese, user_id)
        VALUES (?,?,?,?,?,?,?)
    ''', (ticker, tipo, data, preco, quantidade, tese, user_id))
    conn.commit()
    conn.close()

def listar_decisoes(ticker=None):
    user_id = get_user_id()
    conn = get_connection()
    if ticker:
        rows = conn.execute('SELECT * FROM decisoes WHERE ticker=? AND user_id=? ORDER BY data_decisao DESC', (ticker, user_id)).fetchall()
    else:
        rows = conn.execute('SELECT * FROM decisoes WHERE user_id=? ORDER BY data_decisao DESC', (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def atualizar_resultado(id_decisao, resultado):
    conn = get_connection()
    data_res = datetime.today().strftime('%Y-%m-%d') if resultado else None
    conn.execute('UPDATE decisoes SET resultado=?, data_resultado=? WHERE id=?', (resultado, data_res, id_decisao))
    conn.commit()
    conn.close()

# ==========================================
# HEALTH SCORES (CORREÇÃO DE JSON DUPLO)
# ==========================================

def get_health_scores():
    conn = get_connection()
    rows = conn.execute('SELECT * FROM health_scores').fetchall()
    conn.close()
    return [dict(r) for r in rows]

def salvar_health_score(ticker, score, alertas_payload):
    """
    Guarda o score no banco de dados. 
    A trava 'not isinstance(..., str)' garante que não ocorra dupla codificação (Double JSON).
    """
    if not isinstance(alertas_payload, str):
        alertas_payload = json.dumps(alertas_payload)
        
    conn = get_connection()
    conn.execute('''
        INSERT OR REPLACE INTO health_scores (ticker, score, alertas_venda, atualizado_em) 
        VALUES (?,?,?,CURRENT_TIMESTAMP)
    ''', (ticker, score, alertas_payload))
    conn.commit()
    conn.close()

# ==========================================
# CACHE DE IA
# ==========================================

def salvar_cache_ia(ticker, tipo, conteudo):
    conn = get_connection()
    conn.execute('INSERT INTO cache_analise_ia (ticker, tipo, conteudo) VALUES (?,?,?)', (ticker, tipo, conteudo))
    conn.commit()
    conn.close()

def get_cache_ia(ticker, tipo):
    conn = get_connection()
    row = conn.execute('SELECT conteudo, gerado_em FROM cache_analise_ia WHERE ticker=? AND tipo=? ORDER BY gerado_em DESC LIMIT 1', (ticker, tipo)).fetchone()
    conn.close()
    return dict(row) if row else None