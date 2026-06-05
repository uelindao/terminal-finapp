"""
FinTerminal — camada de acesso a dados via Supabase (PostgreSQL).
Mantém EXATAMENTE as mesmas assinaturas de função que o db_sqlite_legacy.py,
incluindo aliases de compatibilidade nas colunas renomeadas.

Schema: execute database/migrations/001_initial_schema.sql no Supabase Dashboard
antes do primeiro uso.
"""
import json
import sqlite3 as _sqlite3
import os as _os
from datetime import datetime
import hashlib
import streamlit as st
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


# ==========================================
# SESSÕES PERSISTENTES (cross-tab login)
# ==========================================

def criar_sessao(user_id: int, token: str, dias: int = 7) -> bool:
    """Persiste um token de sessão no banco com expiração."""
    from datetime import timezone, timedelta
    sb = get_supabase()
    try:
        expires = (datetime.now(timezone.utc) + timedelta(days=dias)).isoformat()
        sb.table('user_sessions').upsert(
            {'token': token, 'user_id': user_id, 'expires_at': expires},
            on_conflict='token',
        ).execute()
        return True
    except Exception as e:
        logger.error(f"[db] falha ao criar sessão para user {user_id}: {e}")
        return False


def validar_sessao(token: str) -> dict | None:
    """Verifica se token existe, não expirou e retorna dados do usuário."""
    from datetime import timezone
    sb = get_supabase()
    try:
        agora = datetime.now(timezone.utc).isoformat()
        rows = (
            sb.table('user_sessions')
            .select('user_id, expires_at')
            .eq('token', token)
            .gt('expires_at', agora)
            .limit(1)
            .execute()
            .data
        )
        if not rows:
            return None
        user_id = rows[0]['user_id']
        user_rows = (
            sb.table('users')
            .select('id, username, nome, is_admin')
            .eq('id', user_id)
            .limit(1)
            .execute()
            .data
        )
        return user_rows[0] if user_rows else None
    except Exception as e:
        logger.warning(f"[db] falha ao validar sessão: {e}")
        return None


def revogar_sessao(token: str) -> None:
    """Remove o token de sessão do banco (logout)."""
    try:
        get_supabase().table('user_sessions').delete().eq('token', token).execute()
    except Exception as e:
        logger.warning(f"[db] falha ao revogar sessão: {e}")


def limpar_sessoes_expiradas() -> None:
    """Remove sessões expiradas do banco (manutenção periódica)."""
    from datetime import timezone
    try:
        agora = datetime.now(timezone.utc).isoformat()
        get_supabase().table('user_sessions').delete().lt('expires_at', agora).execute()
    except Exception:
        pass


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


def atualizar_tag_ativo(watchlist_id: int, ticker: str, tag: str) -> None:
    """Atualiza a tag/tese de um ativo na watchlist."""
    try:
        get_supabase().table("watchlist_items").update({
            "tag": tag.strip().lower()
        }).eq("watchlist_id", watchlist_id).eq("ticker", ticker).execute()
    except Exception as e:
        logger.warning(f"[db] atualizar_tag {ticker}: {e}")


def listar_tags_watchlist(watchlist_id: int) -> list[str]:
    """Retorna lista ordenada de tags únicas da watchlist."""
    try:
        res = (
            get_supabase()
            .table("watchlist_items")
            .select("tag")
            .eq("watchlist_id", watchlist_id)
            .execute()
        )
        tags = list(set(
            r['tag'] for r in (res.data or [])
            if r.get('tag') and r['tag'] != 'geral'
        ))
        return sorted(tags)
    except Exception as e:
        logger.warning(f"[db] listar_tags: {e}")
        return []


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
    # Sanitiza NaN/Inf para evitar erro no json.dumps do Supabase
    import math as _mt
    def _sn(v):
        if v is None: return None
        try: return None if _mt.isnan(v) or _mt.isinf(v) else v
        except TypeError: return v
    sb.table('portfolio_positions').upsert(
        {
            'ticker': ticker,
            'peso': _sn(peso),
            'preco_medio': _sn(preco_medio),
            'quantidade': _sn(quantidade),
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


# ==========================================
# HISTÓRICO TEMPORAL DE HEALTH SCORES
# ==========================================

# ==========================================
# ALERTAS DE PREÇO
# ==========================================

def listar_alertas(user_id: int = None, limite: int = 20) -> list[dict]:
    """Retorna os alertas de preço do usuário, ordenados por created_at desc."""
    if user_id is None:
        user_id = get_user_id()
    sb = get_supabase()
    try:
        rows = (
            sb.table('alerts')
            .select('*')
            .eq('user_id', user_id)
            .order('created_at', desc=True)
            .limit(limite)
            .execute()
            .data
        )
        # Alias de compatibilidade: created_at → criado_em
        for r in rows:
            r.setdefault('criado_em', r.get('created_at'))
        return rows
    except Exception as e:
        logger.warning(f"[db] falha ao listar alertas do user_id={user_id}: {e}")
        return []


def limpar_cache_ia_antigo(dias: int = 30) -> int:
    """
    Deleta registros de cache de IA mais antigos que `dias` dias.
    Retorna o número de linhas removidas.
    """
    sb = get_supabase()
    try:
        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(days=dias)).isoformat()
        res = (
            sb.table('ai_analysis_cache')
            .delete()
            .lt('created_at', cutoff)
            .execute()
        )
        return len(res.data) if res.data else 0
    except Exception as e:
        logger.warning(f"[db] falha ao limpar cache de IA antigo: {e}")
        return 0


def registrar_historico_score(ticker: str, score: int) -> None:
    """
    Insere um ponto de histórico do health score para o ticker.
    Requer a tabela health_score_history (migration 002).
    """
    sb = get_supabase()
    try:
        sb.table('health_score_history').insert({
            'ticker': ticker,
            'score':  int(score),
        }).execute()
    except Exception as e:
        logger.warning(f"[db] falha ao registrar histórico de score para {ticker}: {e}")


def get_historico_score(ticker: str, dias: int = 180) -> list[dict]:
    """
    Retorna os registros de health score dos últimos `dias` dias para o ticker,
    ordenados por data crescente.
    Cada item tem as chaves: 'score' (int) e 'calculado_em' (str ISO-8601).
    """
    sb = get_supabase()
    try:
        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(days=dias)).isoformat()
        rows = (
            sb.table('health_score_history')
            .select('score, calculado_em')
            .eq('ticker', ticker)
            .gte('calculado_em', cutoff)
            .order('calculado_em')
            .execute()
            .data
        )
        return rows
    except Exception as e:
        logger.warning(f"[db] falha ao buscar histórico de score para {ticker}: {e}")
        return []


# ── rebalanceamento inteligente ──────────────────────────────────────────────

def salvar_peso_alvo(portfolio_id: int, ticker: str, peso_alvo: float):
    """Salva ou atualiza o peso-alvo (%) de um ativo no portfólio."""
    try:
        get_supabase().table("portfolio_targets").upsert(
            {
                "portfolio_id": portfolio_id,
                "ticker":       ticker,
                "peso_alvo":    round(peso_alvo, 2),
                "updated_at":   "now()",
            },
            on_conflict="portfolio_id,ticker",
        ).execute()
    except Exception as e:
        logger.warning(f"[db] salvar_peso_alvo {ticker}: {e}")


def get_pesos_alvo(portfolio_id: int) -> list[dict]:
    """Retorna todos os pesos-alvo de um portfólio."""
    try:
        res = (
            get_supabase()
            .table("portfolio_targets")
            .select("ticker, peso_alvo")
            .eq("portfolio_id", portfolio_id)
            .execute()
        )
        return res.data or []
    except Exception as e:
        logger.warning(f"[db] get_pesos_alvo portfolio_id={portfolio_id}: {e}")
        return []


def deletar_peso_alvo(portfolio_id: int, ticker: str):
    """Remove o peso-alvo de um ativo."""
    try:
        (
            get_supabase()
            .table("portfolio_targets")
            .delete()
            .eq("portfolio_id", portfolio_id)
            .eq("ticker", ticker)
            .execute()
        )
    except Exception as e:
        logger.warning(f"[db] deletar_peso_alvo {ticker}: {e}")


# ── onboarding ───────────────────────────────────────────────────────────────

def is_primeiro_acesso(user_id: int) -> bool:
    """
    Retorna True se o usuário nunca adicionou nenhum ativo à watchlist.
    """
    try:
        wl = (
            get_supabase()
            .table("watchlist_items")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .execute()
        )
        return (wl.count or 0) == 0
    except Exception as e:
        logger.warning(f"[db] is_primeiro_acesso: {e}")
        return False


def marcar_onboarding_completo(user_id: int):
    """Marca que o usuário completou o onboarding."""
    try:
        get_supabase().table("users").update(
            {"onboarding_completo": True}
        ).eq("id", user_id).execute()
    except Exception as e:
        logger.warning(f"[db] marcar_onboarding: {e}")


# ── alertas de health score ───────────────────────────────────────────────────

def salvar_config_alerta(user_id: int, ticker: str, threshold: int):
    """Salva ou atualiza a configuração de alerta para um ativo."""
    try:
        get_supabase().table("alert_config").upsert(
            {
                "user_id":   user_id,
                "ticker":    ticker,
                "threshold": threshold,
                "ativo":     True,
            },
            on_conflict="user_id,ticker",
        ).execute()
    except Exception as e:
        logger.warning(f"[db] salvar_config_alerta: {e}")


def get_configs_alerta(user_id: int) -> list[dict]:
    """Retorna todas as configurações de alerta ativas do usuário."""
    try:
        res = (
            get_supabase()
            .table("alert_config")
            .select("ticker, threshold, ativo")
            .eq("user_id", user_id)
            .eq("ativo", True)
            .execute()
        )
        return res.data or []
    except Exception as e:
        logger.warning(f"[db] get_configs_alerta: {e}")
        return []


def registrar_disparo_alerta(user_id: int, ticker: str,
                              score: int, threshold: int) -> bool:
    """
    Registra um disparo de alerta.
    Retorna False se já disparou nas últimas 24h (anti-spam).
    """
    try:
        from datetime import datetime, timedelta, timezone
        desde = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

        ja_disparou = (
            get_supabase()
            .table("alert_log")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .eq("ticker", ticker)
            .gte("disparado_em", desde)
            .execute()
        )
        if (ja_disparou.count or 0) > 0:
            return False  # já disparou hoje

        get_supabase().table("alert_log").insert(
            {
                "user_id":   user_id,
                "ticker":    ticker,
                "score":     score,
                "threshold": threshold,
            }
        ).execute()
        return True
    except Exception as e:
        logger.warning(f"[db] registrar_disparo_alerta: {e}")
        return False


def deletar_config_alerta(user_id: int, ticker: str):
    """Remove a configuração de alerta para um ativo."""
    try:
        (
            get_supabase()
            .table("alert_config")
            .delete()
            .eq("user_id", user_id)
            .eq("ticker", ticker)
            .execute()
        )
    except Exception as e:
        logger.warning(f"[db] deletar_config_alerta: {e}")


# ── cache de próximas datas de resultado (earnings_dates) ───────────────────

def salvar_earnings_date(ticker: str, data_str: str | None, fonte: str = '') -> None:
    """
    Salva a próxima data de resultado no cache Supabase.
    data_str: formato 'dd/mm/yyyy' ou None.
    Tabela esperada: earnings_dates (ticker PK, proxima_data DATE, fonte TEXT, updated_at TIMESTAMPTZ)
    """
    try:
        from datetime import datetime as _dt
        data_iso = None
        if data_str:
            try:
                data_iso = _dt.strptime(data_str, '%d/%m/%Y').date().isoformat()
            except Exception:
                pass

        get_supabase().table("earnings_dates").upsert(
            {
                "ticker":       ticker,
                "proxima_data": data_iso,
                "fonte":        fonte,
                "updated_at":   "now()",
            },
            on_conflict="ticker",
        ).execute()
    except Exception as e:
        logger.warning(f"[db] salvar_earnings_date {ticker}: {e}")


# ==========================================
# CONFIGURAÇÕES PESSOAIS POR USUÁRIO
# ==========================================

def get_user_settings(user_id: int) -> dict:
    """
    Retorna as configurações de IA e preferências do usuário.
    Sempre devolve um dict com todas as chaves — nunca lança exceção.
    A api_key retornada já está descriptografada (string vazia se ausente).
    """
    defaults: dict = {
        'ai_provider':     'deepseek',
        'ai_api_key':      '',
        'ai_model':        'deepseek-chat',
        'moeda_base':      'BRL',
        'benchmark':       'IBOV',
        'alert_threshold': 40,
    }
    try:
        res = (
            get_supabase()
            .table("user_settings")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        if res.data:
            from utils.crypto import decrypt_key
            d = res.data[0]
            defaults.update({
                'ai_provider':     d.get('ai_provider', 'deepseek'),
                'ai_api_key':      decrypt_key(d.get('ai_api_key_enc', '') or ''),
                'ai_model':        d.get('ai_model', 'deepseek-chat'),
                'moeda_base':      d.get('moeda_base', 'BRL'),
                'benchmark':       d.get('benchmark', 'IBOV'),
                'alert_threshold': d.get('alert_threshold', 40),
            })
    except Exception as e:
        logger.warning(f"[db] get_user_settings user_id={user_id}: {e}")
    return defaults


def salvar_user_settings(user_id: int, settings: dict) -> None:
    """
    Salva (upsert) as configurações do usuário.
    A api_key é criptografada antes de persistir; campo omitido se vazio
    (preserva a chave anterior no banco).
    """
    try:
        from utils.crypto import encrypt_key

        payload: dict = {
            "user_id":         user_id,
            "ai_provider":     settings.get('ai_provider', 'deepseek'),
            "ai_model":        settings.get('ai_model', 'deepseek-chat'),
            "moeda_base":      settings.get('moeda_base', 'BRL'),
            "benchmark":       settings.get('benchmark', 'IBOV'),
            "alert_threshold": int(settings.get('alert_threshold', 40)),
            "updated_at":      "now()",
        }

        api_key_raw = settings.get('ai_api_key', '').strip()
        if api_key_raw:
            enc = encrypt_key(api_key_raw)
            if enc:
                payload["ai_api_key_enc"] = enc

        get_supabase().table("user_settings").upsert(
            payload, on_conflict="user_id"
        ).execute()

    except Exception as e:
        logger.warning(f"[db] salvar_user_settings user_id={user_id}: {e}")


def get_earnings_dates(tickers: list[str]) -> dict:
    """
    Retorna dict {ticker: date} com próximas datas de resultado
    para a lista de tickers fornecida.
    """
    if not tickers:
        return {}
    try:
        from datetime import date as _date
        res = (
            get_supabase()
            .table("earnings_dates")
            .select("ticker, proxima_data")
            .in_("ticker", tickers)
            .execute()
        )
        resultado: dict = {}
        for row in (res.data or []):
            raw = row.get('proxima_data')
            if raw:
                try:
                    resultado[row['ticker']] = _date.fromisoformat(raw)
                except Exception:
                    pass
        return resultado
    except Exception as e:
        logger.warning(f"[db] get_earnings_dates: {e}")
        return {}


# ==========================================
# LOCAL SQLITE STORE (chat portfolio + kv settings)
# ==========================================

_LOCAL_DB_PATH = _os.path.join(_os.path.dirname(__file__), 'local_store.db')


def _get_local_conn():
    conn = _sqlite3.connect(_LOCAL_DB_PATH)
    conn.row_factory = _sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chat_portfolio_historico (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            portfolio_id INTEGER NOT NULL,
            role         TEXT NOT NULL,
            conteudo     TEXT NOT NULL,
            criado_em    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS user_kv (
            user_id INTEGER NOT NULL,
            chave   TEXT NOT NULL,
            valor   TEXT NOT NULL,
            PRIMARY KEY (user_id, chave)
        );
    """)
    conn.commit()
    return conn


def salvar_mensagem_chat(user_id: int, portfolio_id: int, role: str, conteudo: str) -> None:
    try:
        conn = _get_local_conn()
        conn.execute(
            "INSERT INTO chat_portfolio_historico (user_id, portfolio_id, role, conteudo) VALUES (?, ?, ?, ?)",
            (user_id, portfolio_id, role, conteudo),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"[db] salvar_mensagem_chat: {e}")


def get_historico_chat(user_id: int, portfolio_id: int, limite: int = 50) -> list[dict]:
    try:
        conn = _get_local_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT role, conteudo, criado_em FROM chat_portfolio_historico WHERE user_id = ? AND portfolio_id = ? ORDER BY criado_em DESC LIMIT ?",
            (user_id, portfolio_id, limite),
        )
        rows = cur.fetchall()
        conn.close()
        return [{'role': r[0], 'conteudo': r[1], 'criado_em': r[2]} for r in reversed(rows)]
    except Exception as e:
        logger.warning(f"[db] get_historico_chat: {e}")
        return []


def limpar_historico_chat(user_id: int, portfolio_id: int) -> None:
    try:
        conn = _get_local_conn()
        conn.execute(
            "DELETE FROM chat_portfolio_historico WHERE user_id = ? AND portfolio_id = ?",
            (user_id, portfolio_id),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def salvar_user_setting(user_id: int, chave: str, valor: str) -> None:
    try:
        conn = _get_local_conn()
        conn.execute(
            "INSERT OR REPLACE INTO user_kv (user_id, chave, valor) VALUES (?, ?, ?)",
            (user_id, chave, valor),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"[db] salvar_user_setting: {e}")


def get_user_setting(user_id: int, chave: str, default: str = '') -> str:
    try:
        conn = _get_local_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT valor FROM user_kv WHERE user_id = ? AND chave = ?",
            (user_id, chave),
        )
        row = cur.fetchone()
        conn.close()
        return row[0] if row else default
    except Exception as e:
        logger.warning(f"[db] get_user_setting: {e}")
        return default


# ==========================================
# NOVAS TABELAS ETL — price_cache / macro_cache
# ==========================================


@st.cache_data(ttl=3600, show_spinner=False)
def get_price_cache(ticker: str) -> dict | None:
    """Retorna dados de preco da price_cache (se frescos)."""
    try:
        sb = get_supabase()
        res = (
            sb.table("price_cache")
            .select("*")
            .eq("ticker", ticker)
            .execute()
        )
        if res.data:
            return res.data[0]
        return None
    except Exception as e:
        logger.warning(f"[db] get_price_cache {ticker}: {e}")
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def get_all_price_cache() -> dict:
    """Retorna dict {ticker: price_data} de todo o cache de precos."""
    try:
        sb = get_supabase()
        res = sb.table("price_cache").select("*").execute()
        return {r["ticker"]: r for r in (res.data or [])}
    except Exception as e:
        logger.warning(f"[db] get_all_price_cache: {e}")
        return {}


def get_macro_cache(indicator: str) -> float | None:
    """Retorna o valor de um indicador macro especifico."""
    try:
        sb = get_supabase()
        res = (
            sb.table("macro_cache")
            .select("value")
            .eq("indicator", indicator)
            .execute()
        )
        if res.data:
            return float(res.data[0]["value"])
        return None
    except Exception as e:
        logger.warning(f"[db] get_macro_cache {indicator}: {e}")
        return None


@st.cache_data(ttl=900, show_spinner=False)
def get_all_macro_cache() -> dict:
    """Retorna dict {indicator: {value, label, unit}} de todos indicadores macro."""
    try:
        sb = get_supabase()
        res = sb.table("macro_cache").select("*").execute()
        result = {}
        for r in (res.data or []):
            result[r["indicator"]] = {
                "value": float(r["value"]) if r.get("value") is not None else None,
                "label": r.get("label", ""),
                "unit":  r.get("unit", ""),
                "source": r.get("source", ""),
            }
        return result
    except Exception as e:
        logger.warning(f"[db] get_all_macro_cache: {e}")
        return {}


# ==========================================
# ETL LOG — auditoria das sincronizacoes
# ==========================================


def get_ultimo_etl(job_name: str, dias: int = 7) -> dict | None:
    """Retorna o ultimo registro de execucao ETL para um job."""
    try:
        sb = get_supabase()
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
        res = (
            sb.table("etl_log")
            .select("*")
            .eq("job_name", job_name)
            .gte("started_at", cutoff)
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            return res.data[0]
        return None
    except Exception as e:
        logger.warning(f"[db] get_ultimo_etl: {e}")
        return None
