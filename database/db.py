import sqlite3
import json
import os
from datetime import datetime

# garante que a pasta 'data' existe no servidor antes de tentar criar ou ler o banco
os.makedirs('data', exist_ok=True)

def get_connection():
    # liga ao banco de dados permitindo o uso em múltiplas threads (necessário para o streamlit)
    conn = sqlite3.connect('data/finapp.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # tabela da watchlist principal
    c.execute('''
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT UNIQUE NOT NULL,
            nome TEXT NOT NULL,
            mercado TEXT NOT NULL,
            notas TEXT,
            adicionado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # tabela de alertas e gatilhos
    c.execute('''
        CREATE TABLE IF NOT EXISTS alertas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            tipo TEXT NOT NULL,
            threshold REAL NOT NULL,
            ativo INTEGER DEFAULT 1,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            disparado_em TIMESTAMP
        )
    ''')
    
    # tabela de cache para evitar gastos excessivos com a api da ia
    c.execute('''
        CREATE TABLE IF NOT EXISTS cache_analise_ia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            tipo TEXT NOT NULL,
            contexto TEXT,
            conteudo TEXT NOT NULL,
            gerado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # tabela dos health scores quantitativos
    c.execute('''
        CREATE TABLE IF NOT EXISTS health_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT UNIQUE NOT NULL,
            score REAL NOT NULL,
            alertas_venda TEXT,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # tabela com as posições, quantidades e preços médios da sua carteira
    c.execute('''
        CREATE TABLE IF NOT EXISTS portfolio_pesos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT UNIQUE NOT NULL,
            peso REAL DEFAULT 0.0,
            preco_medio REAL DEFAULT 0.0,
            quantidade REAL DEFAULT 0.0,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def popular_watchlist_inicial():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as count FROM watchlist")
    count = c.fetchone()['count']
    
    if count == 0:
        ativos_iniciais = [
            ('ITUB4.SA', 'Itaú Unibanco', 'brasil'),
            ('WEGE3.SA', 'WEG', 'brasil'),
            ('AAPL', 'Apple', 'eua'),
            ('BTC-USD', 'Bitcoin', 'criptomoedas')
        ]
        c.executemany("INSERT INTO watchlist (ticker, nome, mercado) VALUES (?, ?, ?)", ativos_iniciais)
        conn.commit()
    conn.close()

def adicionar_ativo(ticker, nome, mercado):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO watchlist (ticker, nome, mercado) VALUES (?, ?, ?)", (ticker, nome, mercado))
        conn.commit()
    except sqlite3.IntegrityError:
        pass # ignora silenciosamente se o ativo já estiver na lista
    finally:
        conn.close()

def remover_ativo(ticker):
    conn = get_connection()
    c = conn.cursor()
    # apaga o ticker de todas as tabelas para manter o banco limpo
    c.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker,))
    c.execute("DELETE FROM portfolio_pesos WHERE ticker = ?", (ticker,))
    c.execute("DELETE FROM health_scores WHERE ticker = ?", (ticker,))
    c.execute("DELETE FROM alertas WHERE ticker = ?", (ticker,))
    conn.commit()
    conn.close()

def listar_watchlist():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM watchlist ORDER BY mercado, ticker")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def atualizar_notas(ticker, notas):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE watchlist SET notas = ? WHERE ticker = ?", (notas, ticker))
    conn.commit()
    conn.close()

def criar_alerta(ticker, tipo, threshold):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO alertas (ticker, tipo, threshold) VALUES (?, ?, ?)", (ticker, tipo, float(threshold)))
    conn.commit()
    conn.close()

def listar_alertas():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM alertas ORDER BY criado_em DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def desativar_alerta(alerta_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE alertas SET ativo = 0 WHERE id = ?", (alerta_id,))
    conn.commit()
    conn.close()

def marcar_disparado(alerta_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE alertas SET disparado_em = CURRENT_TIMESTAMP WHERE id = ?", (alerta_id,))
    conn.commit()
    conn.close()

def salvar_cache_ia(ticker, tipo, conteudo, contexto="geral"):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO cache_analise_ia (ticker, tipo, contexto, conteudo) 
        VALUES (?, ?, ?, ?)
    ''', (ticker, tipo, contexto, conteudo))
    conn.commit()
    conn.close()

def get_cache_ia(ticker, tipo, max_horas=24):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT conteudo, gerado_em 
        FROM cache_analise_ia 
        WHERE ticker = ? AND tipo = ? 
        ORDER BY gerado_em DESC LIMIT 1
    ''', (ticker, tipo))
    row = c.fetchone()
    conn.close()
    
    if row:
        try:
            gerado_em = datetime.strptime(row['gerado_em'], '%Y-%m-%d %H:%M:%S')
            diferenca = datetime.utcnow() - gerado_em
            if diferenca.total_seconds() <= max_horas * 3600:
                return row['conteudo']
        except:
            pass
    return None

def salvar_health_score(ticker, score, alertas_venda):
    conn = get_connection()
    c = conn.cursor()
    alertas_json = json.dumps(alertas_venda)
    c.execute('''
        INSERT INTO health_scores (ticker, score, alertas_venda, atualizado_em) 
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(ticker) DO UPDATE SET 
            score = excluded.score, 
            alertas_venda = excluded.alertas_venda,
            atualizado_em = CURRENT_TIMESTAMP
    ''', (ticker, score, alertas_json))
    conn.commit()
    conn.close()

def get_health_scores():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM health_scores")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def salvar_peso(ticker, peso, preco_medio, quantidade):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO portfolio_pesos (ticker, peso, preco_medio, quantidade, atualizado_em) 
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(ticker) DO UPDATE SET 
            peso = excluded.peso,
            preco_medio = excluded.preco_medio,
            quantidade = excluded.quantidade,
            atualizado_em = CURRENT_TIMESTAMP
    ''', (ticker, float(peso), float(preco_medio), float(quantidade)))
    conn.commit()
    conn.close()

def get_pesos():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM portfolio_pesos")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]