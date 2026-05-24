"""
FinTerminal — camada de acesso a dados via Supabase (PostgreSQL).
Mantém EXATAMENTE as mesmas assinaturas de função que o db_sqlite_legacy.py,
incluindo aliases de compatibilidade nas colunas renomeadas.

Schema: execute database/migrations/001_initial_schema.sql no Supabase Dashboard
antes do primeiro uso.
"""
import json
from datetime import datetime
import hashlib
from database.supabase_client import get_supabase
from utils.logger import get_logger

logger = get_logger(__name__)


def get_user_id() -> int:
    """Retorna o user_id da sessão atual ou 1 (admin) como fallback."""
    try:
        import streamlit as st
        return st.session_state.get('user_id', 1)
    except Exception as e:
        logger.warning(f"[db] falha ao obter user_id da sessão, usando fallback 1: {e}")
        return 1


# ==========================================
# AUTENTICAÇÃO E GESTÃO DE UTILIZADORES
# ==========================================

def _hash_senha(senha: str, salt: str = "finterminal_2025") -> str:
    return hashlib.sha256(f"{salt}{senha}".encode()).hexdigest()


def criar_usuario(username: str, senha: str, nome: str = "", email: str = "", is_admin: bool = False) -> bool:
    sb = get_supabase()
    try:
        sb.table('users').insert({
            'username': username.lower().strip(),
            'senha_hash': _hash_senha(senha),
            'nome': nome,
            'email': email,
            'is_admin': is_admin,
        }).execute()
        return True
    except Exception as e:
        logger.error(f"[db] falha ao criar usuário '{username}': {e}")
        return False


def autenticar_usuario(username: str, senha: str) -> dict | None:
    sb = get_supabase()
    try:
        rows = (
            sb.table('users')
            .select('id, username, nome, email, is_admin')
            .eq('username', username.lower().strip())
            .eq('senha_hash', _hash_senha(senha))
            .execute()
            .data
        )
        if rows:
            user = rows[0]
            try:
                sb.table('users').update(
                    {'ultimo_login': datetime.utcnow().isoformat()}
                ).eq('id', user['id']).execute()
            except Exception as e:
                logger.warning(f"[db] falha ao atualizar ultimo_login do user {user['id']}: {e}")
            return user
        return None
    except Exception as e:
        logger.error(f"[db] falha na autenticação do usuário '{username}': {e}")
        return None


def listar_usuarios() -> list[dict]:
    sb = get_supabase()
    try:
        rows = (
            sb.table('users')
            .select('id, username, nome, email, is_admin, created_at, ultimo_login')
            .order('created_at')
            .execute()
            .data
        )
        # Alias de compatibilidade: created_at → criado_em
        for r in rows:
            r.setdefault('criado_em', r.get('created_at'))
        return rows
    except Exception as e:
        logger.error(f"[db] falha ao listar usuários: {e}")
        return []


def alterar_senha(user_id: int, nova_senha: str) -> None:
    sb = get_supabase()
    try:
        sb.table('users').update(
            {'senha_hash': _hash_senha(nova_senha)}
        ).eq('id', user_id).execute()
    except Exception as e:
        logger.error(f"[db] falha ao alterar senha do user_id={user_id}: {e}")


def deletar_usuario(user_id: int) -> None:
    sb = get_supabase()
    tabelas = [
        'watchlist_items', 'alerts', 'portfolio_positions', 'decision_log',
        'saved_comparisons', 'watchlists', 'portfolios', 'report_history',
    ]
    for tabela in tabelas:
        try:
            sb.table(tabela).delete().eq('user_id', user_id).execute()
        except Exception as e:
            logger.warning(f"[db] falha ao limpar tabela '{tabela}' para user_id={user_id}: {e}")
    try:
        sb.table('users').delete().eq('id', user_id).execute()
    except Exception as e:
        logger.error(f"[db] falha ao deletar usuário user_id={user_id}: {e}")


def _criar_admin_padrao():
    sb = get_supabase()
    try:
        rows = sb.table('users').select('id').eq('is_admin', True).execute().data
        if len(rows) == 0:
            try:
                import streamlit as st
                try:
                    senha_padrao = st.secrets["admin"]["password"]
                except (KeyError, AttributeError):
                    senha_padrao = 'admin123'
            except Exception as e:
                logger.warning(f"[db] falha ao ler senha admin dos secrets, usando padrão: {e}")
                senha_padrao = 'admin123'

            sb.table('users').insert({
                'username': 'admin',
                'senha_hash': _hash_senha(senha_padrao),
                'nome': 'administrador',
                'is_admin': True,
            }).execute()
            logger.info("[db] usuário admin padrão criado.")
    except Exception as e:
        logger.error(f"[db] falha ao criar admin padrão: {e}")


# ==========================================
# INICIALIZAÇÃO DA BASE DE DADOS
# ==========================================

def init_db():
    """
    Verifica a conexão com Supabase e garante o admin padrão.

    O schema NÃO é criado automaticamente aqui — execute antes:
        database/migrations/001_initial_schema.sql
    no Supabase Dashboard → SQL Editor.
    """
    try:
        sb = get_supabase()
        sb.table('users').select('id').limit(1).execute()
        logger.info("[db] Supabase conectado e schema validado.")
        _criar_admin_padrao()
        _migrar_watchlist_para_default()
        _migrar_portfolio_para_default()
    except Exception as e:
        logger.error(
            f"[db] falha na inicialização do Supabase: {e}. "
            "Execute database/migrations/001_initial_schema.sql no Supabase Dashboard."
        )
        raise


def _migrar_watchlist_para_default():
    """No-op: o schema Supabase já nasce com estrutura correta."""
    pass


def _migrar_portfolio_para_default():
    """No-op: o schema Supabase já nasce com estrutura correta."""
    pass


# ==========================================
# CACHE DE FUNDAMENTOS
# ==========================================

def salvar_fundamento_cache(ticker: str, dados: dict):
    sb = get_supabase()
    try:
        sb.table('fundamentals_cache').upsert(
            {'ticker': ticker, 'dados_json': json.dumps(dados)},
            on_conflict='ticker',
        ).execute()
    except Exception as e:
        logger.warning(f"[db] falha ao salvar cache de fundamentos para {ticker}: {e}")


def get_todos_fundamentos_cache() -> dict:
    sb = get_supabase()
    try:
        rows = sb.table('fundamentals_cache').select('ticker, dados_json').execute().data
        return {
            r['ticker']: json.loads(r['dados_json'])
            for r in rows
            if r.get('dados_json')
        }
    except Exception as e:
        logger.warning(f"[db] falha ao carregar cache de fundamentos: {e}")
        return {}


# ==========================================
# GESTÃO DE WATCHLISTS (COLEÇÕES)
# ==========================================

def criar_watchlist(nome: str, descricao: str = "", cor: str = "#FF9900", icone: str = "⭐") -> int:
    user_id = get_user_id()
    sb = get_supabase()
    response = sb.table('watchlists').insert({
        'user_id': user_id, 'nome': nome,
        'descricao': descricao, 'cor': cor, 'icone': icone,
    }).execute()
    return response.data[0]['id']


def listar_watchlists() -> list[dict]:
    user_id = get_user_id()
    sb = get_supabase()

    watchlists = (
        sb.table('watchlists').select('*').eq('user_id', user_id).execute().data
    )
    # Ordenação: padrao True primeiro, depois por created_at asc
    watchlists.sort(key=lambda x: (not bool(x.get('padrao')), x.get('created_at') or ''))

    # Contagem de itens por watchlist (evita JOIN)
    items = (
        sb.table('watchlist_items')
        .select('watchlist_id')
        .eq('user_id', user_id)
        .execute()
        .data
    )
    counts: dict[int, int] = {}
    for item in items:
        wid = item['watchlist_id']
        counts[wid] = counts.get(wid, 0) + 1

    for wl in watchlists:
        wl['total_ativos'] = counts.get(wl['id'], 0)
        wl.setdefault('criado_em', wl.get('created_at'))   # alias de compat.

    return watchlists


def renomear_watchlist(watchlist_id: int, novo_nome: str, nova_descricao: str = "", novo_icone: str = "⭐", nova_cor: str = "#FF9900") -> None:
    user_id = get_user_id()
    sb = get_supabase()
    sb.table('watchlists').update({
        'nome': novo_nome, 'descricao': nova_descricao,
        'icone': novo_icone, 'cor': nova_cor,
    }).eq('id', watchlist_id).eq('user_id', user_id).execute()


def deletar_watchlist(watchlist_id: int) -> None:
    user_id = get_user_id()
    sb = get_supabase()
    sb.table('watchlist_items').delete().eq('watchlist_id', watchlist_id).eq('user_id', user_id).execute()
    sb.table('watchlists').delete().eq('id', watchlist_id).eq('user_id', user_id).execute()


def get_watchlist_padrao() -> int:
    user_id = get_user_id()
    sb = get_supabase()

    rows = (
        sb.table('watchlists').select('id, padrao, created_at')
        .eq('user_id', user_id)
        .execute()
        .data
    )
    if rows:
        rows.sort(key=lambda x: (not bool(x.get('padrao')), x.get('created_at') or ''))
        return rows[0]['id']

    # Cria watchlist padrão se não existir
    response = sb.table('watchlists').insert({
        'user_id': user_id, 'nome': 'principal',
        'icone': '⭐', 'cor': '#FF9900', 'padrao': True,
    }).execute()
    return response.data[0]['id']


def definir_watchlist_padrao(watchlist_id: int) -> None:
    user_id = get_user_id()
    sb = get_supabase()
    sb.table('watchlists').update({'padrao': False}).eq('user_id', user_id).execute()
    sb.table('watchlists').update({'padrao': True}).eq('id', watchlist_id).eq('user_id', user_id).execute()


# ==========================================
# ATIVOS (CRUD NA WATCHLIST)
# ==========================================

def adicionar_ativo(ticker: str, nome: str = "", mercado: str = "", watchlist_id: int = None) -> None:
    user_id = get_user_id()
    if watchlist_id is None:
        watchlist_id = get_watchlist_padrao()
    sb = get_supabase()
    try:
        sb.table('watchlist_items').insert({
            'ticker': ticker, 'nome': nome, 'mercado': mercado,
            'user_id': user_id, 'watchlist_id': watchlist_id,
        }).execute()
    except Exception as e:
        # UNIQUE(ticker, user_id, watchlist_id) — duplicata ignorada silenciosamente
        logger.warning(f"[db] ativo {ticker} já existe na watchlist {watchlist_id} (user={user_id}): {e}")


def remover_ativo(ticker: str, watchlist_id: int = None) -> None:
    user_id = get_user_id()
    sb = get_supabase()
    query = sb.table('watchlist_items').delete().eq('ticker', ticker).eq('user_id', user_id)
    if watchlist_id:
        query = query.eq('watchlist_id', watchlist_id)
    query.execute()


def listar_watchlist(watchlist_id: int = None) -> list[dict]:
    user_id = get_user_id()
    sb = get_supabase()
    query = (
        sb.table('watchlist_items').select('*')
        .eq('user_id', user_id)
        .order('created_at', desc=True)
    )
    if watchlist_id is not None:
        query = query.eq('watchlist_id', watchlist_id)
    rows = query.execute().data
    # Alias de compatibilidade: created_at → adicionado_em
    for r in rows:
        r.setdefault('adicionado_em', r.get('created_at'))
    return rows


def atualizar_notas(ticker, notas, watchlist_id):
    user_id = get_user_id()
    sb = get_supabase()
    sb.table('watchlist_items').update({'notas': notas}).eq(
        'ticker', ticker,
    ).eq('user_id', user_id).eq('watchlist_id', watchlist_id).execute()


def popular_watchlist_inicial():
    user_id = get_user_id()
    sb = get_supabase()
    count = len(sb.table('watchlist_items').select('ticker').eq('user_id', user_id).execute().data)
    if count == 0:
        wl_id = get_watchlist_padrao()
        ativos = [
            ('PETR4.SA', 'petrobras', 'brasil'),
            ('ITUB4.SA', 'itaú unibanco', 'brasil'),
            ('AAPL', 'apple inc.', 'eua'),
        ]
        for t, n, m in ativos:
            try:
                sb.table('watchlist_items').insert({
                    'ticker': t, 'nome': n, 'mercado': m,
                    'user_id': user_id, 'watchlist_id': wl_id,
                }).execute()
            except Exception as e:
                logger.warning(f"[db] falha ao inserir ativo inicial {t}: {e}")


# ==========================================
# GESTÃO DE PORTFÓLIOS (MÚLTIPLOS)
# ==========================================

def criar_portfolio(nome: str, descricao: str = "", cor: str = "#FF9900", icone: str = "💼") -> int:
    user_id = get_user_id()
    sb = get_supabase()
    response = sb.table('portfolios').insert({
        'user_id': user_id, 'nome': nome,
        'descricao': descricao, 'cor': cor, 'icone': icone,
    }).execute()
    return response.data[0]['id']


def listar_portfolios() -> list[dict]:
    user_id = get_user_id()
    sb = get_supabase()

    portfolios = sb.table('portfolios').select('*').eq('user_id', user_id).execute().data
    portfolios.sort(key=lambda x: (not bool(x.get('padrao')), x.get('created_at') or ''))

    # Contagem de posições com quantidade > 0
    positions = (
        sb.table('portfolio_positions')
        .select('portfolio_id, quantidade')
        .eq('user_id', user_id)
        .execute()
        .data
    )
    counts: dict[int, int] = {}
    for pos in positions:
        if (pos.get('quantidade') or 0) > 0:
            pid = pos['portfolio_id']
            counts[pid] = counts.get(pid, 0) + 1

    for pf in portfolios:
        pf['total_ativos'] = counts.get(pf['id'], 0)
        pf.setdefault('criado_em', pf.get('created_at'))   # alias de compat.

    return portfolios


def get_portfolio_padrao() -> int:
    user_id = get_user_id()
    sb = get_supabase()

    rows = (
        sb.table('portfolios').select('id, padrao, created_at')
        .eq('user_id', user_id)
        .execute()
        .data
    )
    if rows:
        rows.sort(key=lambda x: (not bool(x.get('padrao')), x.get('created_at') or ''))
        return rows[0]['id']

    response = sb.table('portfolios').insert({
        'user_id': user_id, 'nome': 'principal',
        'icone': '💼', 'cor': '#FF9900', 'padrao': True,
    }).execute()
    return response.data[0]['id']


def definir_portfolio_padrao(portfolio_id: int) -> None:
    user_id = get_user_id()
    sb = get_supabase()
    sb.table('portfolios').update({'padrao': False}).eq('user_id', user_id).execute()
    sb.table('portfolios').update({'padrao': True}).eq('id', portfolio_id).eq('user_id', user_id).execute()


def renomear_portfolio(portfolio_id: int, novo_nome: str, nova_descricao: str = "", novo_icone: str = "💼", nova_cor: str = "#FF9900") -> None:
    user_id = get_user_id()
    sb = get_supabase()
    sb.table('portfolios').update({
        'nome': novo_nome, 'descricao': nova_descricao,
        'icone': novo_icone, 'cor': nova_cor,
    }).eq('id', portfolio_id).eq('user_id', user_id).execute()


def deletar_portfolio(portfolio_id: int) -> None:
    user_id = get_user_id()
    sb = get_supabase()
    sb.table('portfolio_positions').delete().eq('portfolio_id', portfolio_id).eq('user_id', user_id).execute()
    sb.table('portfolios').delete().eq('id', portfolio_id).eq('user_id', user_id).execute()


# ==========================================
# PORTFÓLIO E DECISÕES
# ==========================================

def salvar_peso(ticker, peso, preco_medio=None, quantidade=None, portfolio_id=None):
    user_id = get_user_id()
    if portfolio_id is None:
        portfolio_id = get_portfolio_padrao()
    sb = get_supabase()
    sb.table('portfolio_positions').upsert(
        {
            'ticker': ticker, 'peso': peso,
            'preco_medio': preco_medio, 'quantidade': quantidade,
            'user_id': user_id, 'portfolio_id': portfolio_id,
        },
        on_conflict='ticker,user_id,portfolio_id',
    ).execute()


def get_pesos(portfolio_id=None):
    user_id = get_user_id()
    if portfolio_id is None:
        portfolio_id = get_portfolio_padrao()
    sb = get_supabase()
    rows = (
        sb.table('portfolio_positions').select('*')
        .eq('user_id', user_id)
        .eq('portfolio_id', portfolio_id)
        .execute()
        .data
    )
    # Alias de compatibilidade: updated_at → atualizado_em
    for r in rows:
        r.setdefault('atualizado_em', r.get('updated_at'))
    return rows


def registrar_decisao(ticker, tipo, data, preco, quantidade, tese):
    user_id = get_user_id()
    sb = get_supabase()
    sb.table('decision_log').insert({
        'ticker': ticker, 'tipo': tipo, 'data_decisao': data,
        'preco_decisao': preco, 'quantidade': quantidade,
        'tese': tese, 'user_id': user_id,
    }).execute()


def listar_decisoes(ticker=None):
    user_id = get_user_id()
    sb = get_supabase()
    query = (
        sb.table('decision_log').select('*')
        .eq('user_id', user_id)
        .order('data_decisao', desc=True)
    )
    if ticker:
        query = query.eq('ticker', ticker)
    return query.execute().data


def atualizar_resultado(id_decisao, resultado):
    sb = get_supabase()
    data_res = datetime.today().strftime('%Y-%m-%d') if resultado else None
    sb.table('decision_log').update({
        'resultado': resultado,
        'data_resultado': data_res,
    }).eq('id', id_decisao).execute()


# ==========================================
# HEALTH SCORES
# ==========================================

def get_health_scores():
    sb = get_supabase()
    rows = sb.table('health_scores').select('*').execute().data
    # Alias de compatibilidade: updated_at → atualizado_em
    for r in rows:
        r.setdefault('atualizado_em', r.get('updated_at'))
    return rows


def salvar_health_score(ticker, score, alertas_payload):
    """
    Guarda o score no banco de dados.
    A trava 'not isinstance(..., str)' garante que não ocorra dupla codificação (Double JSON).
    """
    if not isinstance(alertas_payload, str):
        alertas_payload = json.dumps(alertas_payload)
    sb = get_supabase()
    sb.table('health_scores').upsert(
        {'ticker': ticker, 'score': score, 'alertas_venda': alertas_payload},
        on_conflict='ticker',
    ).execute()


# ==========================================
# CACHE DE IA
# ==========================================

def salvar_cache_ia(ticker, tipo, conteudo):
    sb = get_supabase()
    sb.table('ai_analysis_cache').insert({
        'ticker': ticker, 'tipo': tipo, 'conteudo': conteudo,
    }).execute()


def get_cache_ia(ticker, tipo):
    sb = get_supabase()
    rows = (
        sb.table('ai_analysis_cache').select('conteudo, created_at')
        .eq('ticker', ticker)
        .eq('tipo', tipo)
        .order('created_at', desc=True)
        .limit(1)
        .execute()
        .data
    )
    if rows:
        # Alias de compatibilidade: created_at → gerado_em (igual ao SQLite)
        return {'conteudo': rows[0]['conteudo'], 'gerado_em': rows[0]['created_at']}
    return None


# ==========================================
# RELATÓRIOS SEMANAIS
# ==========================================

def registrar_envio_relatorio(tickers: list[str], tipo: str = 'semanal') -> None:
    user_id = get_user_id()
    sb = get_supabase()
    sb.table('report_history').insert({
        'user_id': user_id, 'tipo': tipo,
        'tickers_incluidos': ','.join(tickers),
    }).execute()


def get_ultimo_envio_relatorio(tipo: str = 'semanal') -> dict | None:
    user_id = get_user_id()
    sb = get_supabase()
    rows = (
        sb.table('report_history').select('*')
        .eq('user_id', user_id)
        .eq('tipo', tipo)
        .order('created_at', desc=True)
        .limit(1)
        .execute()
        .data
    )
    if rows:
        rows[0].setdefault('enviado_em', rows[0].get('created_at'))  # alias de compat.
        return rows[0]
    return None


def listar_relatorios_enviados(limite: int = 10) -> list[dict]:
    user_id = get_user_id()
    sb = get_supabase()
    rows = (
        sb.table('report_history').select('*')
        .eq('user_id', user_id)
        .order('created_at', desc=True)
        .limit(limite)
        .execute()
        .data
    )
    # Alias de compatibilidade: created_at → enviado_em
    for r in rows:
        r.setdefault('enviado_em', r.get('created_at'))
    return rows
