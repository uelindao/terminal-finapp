import streamlit as st
import yfinance as yf
import pandas as pd
import json
import time
import requests
from datetime import datetime
import logging

# silenciar alertas vermelhos do yahoo finance no terminal
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# importações do ecossistema finapp
from utils.auth import require_auth, render_user_badge, get_current_user
from utils.style import aplicar_tema
from database.db import (
    init_db, popular_watchlist_inicial, listar_watchlist,
    remover_ativo, adicionar_ativo, atualizar_notas,
    get_health_scores, get_pesos,
    listar_watchlists, criar_watchlist, renomear_watchlist,
    deletar_watchlist, definir_watchlist_padrao, get_watchlist_padrao,
    registrar_envio_relatorio, get_ultimo_envio_relatorio, listar_relatorios_enviados,
    is_primeiro_acesso, marcar_onboarding_completo,
    get_earnings_dates, salvar_earnings_date,
    listar_tags_watchlist, atualizar_tag_ativo,
)
from utils.email_sender import enviar_relatorio_semanal
from utils.health_engine import calcular_health_score, _is_fii
from utils.earnings_scraper import buscar_resultados
from utils.tickers import mapear_ticker_base

from utils.components import (
    page_header, section_title, metric_card,
    watchlist_card, watchlist_row, watchlist_header_row,
    empty_state, progress_steps,
    status_card, inject_keyboard_shortcuts, auto_refresh_indicator
)
from utils.formatters import fmt_preco, fmt_pct
import plotly.graph_objects as go
from utils.charts import base_layout
from utils.notificacoes import (solicitar_permissao_notificacao,
                                 verificar_e_disparar_alertas)
from utils.macro_context import garantir_macro_context


@st.cache_data(ttl=300, show_spinner=False)
def buscar_cotacoes_lote(tickers_tuple: tuple) -> dict:
    """
    Busca preço atual e variação do dia para uma lista de tickers.
    Cache de 5 minutos. Retorna dict: {ticker: {preco, var_1d, volume}}
    """
    tickers = list(tickers_tuple)
    resultado = {}
    if not tickers:
        return resultado
    try:
        from utils.tickers import mapear_ticker_base
        tickers_base = [mapear_ticker_base(t) for t in tickers]
        hist = yf.download(
            tickers_base,
            period="2d",
            auto_adjust=True,
            progress=False,
            multi_level_index=False,
        )
        close = hist.get('Close', hist)
        volume = hist.get('Volume', None)

        for i, t in enumerate(tickers):
            tb = tickers_base[i]
            try:
                if isinstance(close, pd.DataFrame):
                    serie = close[tb].dropna() if tb in close.columns else pd.Series()
                else:
                    serie = close.dropna()

                if len(serie) < 1:
                    continue

                preco_atual = float(serie.iloc[-1])
                preco_ant   = float(serie.iloc[-2]) if len(serie) >= 2 else preco_atual
                var_1d      = ((preco_atual / preco_ant) - 1) * 100 if preco_ant > 0 else 0.0

                vol = None
                if volume is not None and isinstance(volume, pd.DataFrame):
                    if tb in volume.columns:
                        vol = float(volume[tb].dropna().iloc[-1])

                resultado[t] = {
                    'preco': round(preco_atual, 2),
                    'var_1d': round(var_1d, 2),
                    'volume': vol,
                }
            except Exception:
                continue
    except Exception:
        pass
    return resultado


@st.cache_data(ttl=3600, show_spinner=False)
def buscar_earnings_proximos(tickers_tuple: tuple) -> dict:
    """
    Retorna dict {ticker: dias_ate_earnings} para ativos
    com resultado nos próximos 14 dias.
    Usa o banco de dados local (salvo pelo earnings_scraper).
    """
    import datetime
    resultado = {}
    try:
        from database.db import get_earnings_dates
        tickers = list(tickers_tuple)
        hoje    = datetime.date.today()

        for ticker in tickers:
            try:
                data_str = get_earnings_dates(ticker)
                if not data_str:
                    continue
                dt = None
                for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%m/%d/%Y']:
                    try:
                        dt = datetime.datetime.strptime(data_str, fmt).date()
                        break
                    except ValueError:
                        pass
                if dt is None:
                    continue
                dias = (dt - hoje).days
                if 0 <= dias <= 14:
                    resultado[ticker] = dias
            except Exception:
                continue
    except Exception:
        pass
    return resultado


@st.cache_data(ttl=1800, show_spinner=False)
def calcular_oportunidades_watchlist(tickers_tuple: tuple) -> list[dict]:
    """
    Identifica ativos da watchlist com maior assimetria positiva:
    health score alto + momentum recente positivo + longe do topo 52w.
    Retorna top 3 ordenados por score de assimetria composto.
    """
    tickers = list(tickers_tuple)
    if not tickers:
        return []

    from database.db import get_health_scores, get_todos_fundamentos_cache
    from utils.tickers import mapear_ticker_base

    hs_all   = {h['ticker']: h for h in (get_health_scores() or [])}
    fund_all = get_todos_fundamentos_cache()

    resultados = []

    for ticker in tickers:
        t_base = mapear_ticker_base(ticker)
        hs_row = hs_all.get(t_base) or hs_all.get(ticker)
        if not hs_row:
            continue

        score_hs = hs_row.get('score', 50)
        if score_hs < 55:   # só considera ativos com score razoável
            continue

        try:
            hist = yf.Ticker(t_base).history(period="1y", auto_adjust=True)
            if hist.empty or len(hist) < 60:
                continue

            close       = hist['Close']
            preco_atual = float(close.iloc[-1])
            preco_1m    = float(close.iloc[-21]) if len(close) >= 21 else preco_atual
            preco_3m    = float(close.iloc[-63]) if len(close) >= 63 else preco_atual
            high_52w    = float(close.max())

            ret_1m   = (preco_atual / preco_1m - 1) * 100
            ret_3m   = (preco_atual / preco_3m - 1) * 100
            dist_top = (preco_atual / high_52w - 1) * 100

            # Filtro obrigatório de momentum mínimo
            if ret_1m < -15 and ret_3m < 0:
                continue   # queda forte em ambos os períodos — tendência baixista
            if ret_1m <= 0 and ret_3m <= 0:
                continue   # sem momentum em nenhum período — não é oportunidade

            # Score de assimetria composto (0-100)
            pts_hs = min(40, (score_hs / 100) * 40)
            pts_mom = 0
            if ret_1m > 0:  pts_mom += 15
            if ret_3m > 0:  pts_mom += 15

            # Distância do topo (peso 30%) — penaliza quedas rápidas
            if dist_top < -30:
                preco_6m = float(close.iloc[-126]) if len(close) >= 126 else preco_atual
                ret_6m   = (preco_atual / preco_6m - 1) * 100
                if ret_6m < -25:
                    pts_top = 10   # queda rápida nos últimos 6m — penaliza
                else:
                    pts_top = 30   # queda acumulada de longo prazo — pode ser desconto real
            elif dist_top < -15:
                pts_top = 20
            elif dist_top < -5:
                pts_top = 10
            else:
                pts_top = 3

            score_assim = round(pts_hs + pts_mom + pts_top, 1)

            fund_d = fund_all.get(t_base, {})
            nome   = fund_d.get('nome') or ticker.replace('.SA', '')
            setor  = fund_d.get('setor') or '—'

            resultados.append({
                'ticker':       ticker,
                'nome':         nome[:28],
                'setor':        setor,
                'score_hs':     score_hs,
                'score_assim':  score_assim,
                'ret_1m':       round(ret_1m, 2),
                'ret_3m':       round(ret_3m, 2),
                'dist_top':     round(dist_top, 2),
                'preco_atual':  round(preco_atual, 2),
                'mercado':      'BR' if ticker.endswith('.SA') else 'EUA',
            })

        except Exception:
            continue

    return sorted(resultados, key=lambda x: x['score_assim'], reverse=True)[:5]


# 1. configuração da página (tem de ser o primeiro comando)
st.set_page_config(page_title="terminal finapp | home", layout="wide", initial_sidebar_state="expanded", page_icon="🏠")

# 1.5 CRIAR AS TABELAS NO BANCO DE DADOS ANTES DE QUALQUER COISA (CORREÇÃO PARA A NUVEM)
init_db()
popular_watchlist_inicial()

# 2. barreira de segurança multi-usuário
if not require_auth():
    st.stop()

# 3. renderizações pós-login
render_user_badge()
aplicar_tema()
inject_keyboard_shortcuts()

# Garante macro_context atualizado em todas as páginas filhas
garantir_macro_context()

# Solicita permissão de notificação browser (uma vez por sessão)
if not st.session_state.get('notif_permission_asked'):
    solicitar_permissao_notificacao()
    st.session_state['notif_permission_asked'] = True

# Verifica alertas de health score ao carregar a página
_user_notif = get_current_user()
if _user_notif:
    _health_all = get_health_scores()
    if _health_all:
        verificar_e_disparar_alertas(_user_notif['user_id'], _health_all)

def buscar_ativo_yahoo(query):
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}"
    headers = {'user-agent': 'Mozilla/5.0'}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        return r.json().get('quotes', [])
    except:
        return []

# ==========================================
# HEADER E PAINÉIS DE UTILIZADOR
# ==========================================
page_header("🏠 terminal finapp", "centro de comando: mercado global, resumo do portfólio e watchlist.")

# ── Admin e Perfil na sidebar ───────────────────────────────────────────
with st.sidebar:
    _user_sidebar = get_current_user()

    # Perfil compacto
    if _user_sidebar:
        with st.expander("👤 meu perfil", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**usuário:** {_user_sidebar['username']}")
                st.markdown(f"**nome:** {_user_sidebar['nome'] or '—'}")
                st.markdown(f"**perfil:** {'administrador' if _user_sidebar['is_admin'] else 'usuário'}")
            with c2:
                with st.form("form_minha_senha", clear_on_submit=True):
                    st.markdown("**alterar senha:**")
                    senha_atual = st.text_input("senha atual:", type="password", key="sb_pwd_atual")
                    senha_nova  = st.text_input("nova senha:", type="password", key="sb_pwd_nova")
                    senha_conf  = st.text_input("confirmar:", type="password", key="sb_pwd_conf")
                    if st.form_submit_button("alterar senha"):
                        from database.db import autenticar_usuario, alterar_senha
                        if autenticar_usuario(_user_sidebar['username'], senha_atual):
                            if senha_nova == senha_conf and len(senha_nova) >= 4:
                                alterar_senha(_user_sidebar['user_id'], senha_nova)
                                st.success("✅ senha alterada!")
                            elif senha_nova != senha_conf:
                                st.error("senhas não coincidem.")
                            else:
                                st.error("mínimo 4 caracteres.")
                        else:
                            st.error("senha atual incorreta.")

    # ── CARD DE REGIME MACRO ─────────────────────────────────────────────
    _macro_home = st.session_state.get("macro_context", {})
    if _macro_home:
        _selic_h = _macro_home.get("selic", 10.75)
        _vix_h   = _macro_home.get("vix", 15.0)
        _ipca_h  = _macro_home.get("ipca", 4.5)
        _label_h = _macro_home.get("label", "neutro")

        # Cor do regime
        _cor_regime = (
            "#FF1744" if "stress" in _label_h
            else "#FF9900" if "altos" in _label_h
            else "#00C853"
        )

        # Ícone do VIX
        _icone_vix = "🔴" if _vix_h > 25 else ("🟡" if _vix_h > 18 else "🟢")

        st.markdown(
            f'<div style="background:#0d0d0d; border:1px solid #1e1e1e; '
            f'border-left:3px solid {_cor_regime}; border-radius:6px; '
            f'padding:12px 20px; margin-bottom:20px; '
            f'display:flex; align-items:center; gap:32px; flex-wrap:wrap;">'

            f'<div style="font-family:Courier New; font-size:0.68rem; '
            f'color:#555; text-transform:uppercase; letter-spacing:.1em; '
            f'min-width:80px;">regime macro</div>'

            f'<div style="font-family:Courier New; font-size:0.82rem; '
            f'color:{_cor_regime}; font-weight:600;">{_label_h}</div>'

            f'<div style="display:flex; gap:24px; margin-left:auto; flex-wrap:wrap;">'

            f'<div style="text-align:center;">'
            f'<div style="font-size:0.65rem; color:#444; '
            f'text-transform:uppercase;">selic</div>'
            f'<div style="font-size:0.9rem; color:#FF9900; '
            f'font-family:Courier New; font-weight:600;">'
            f'{_selic_h:.2f}%</div>'
            f'</div>'

            f'<div style="text-align:center;">'
            f'<div style="font-size:0.65rem; color:#444; '
            f'text-transform:uppercase;">ipca</div>'
            f'<div style="font-size:0.9rem; color:#ccc; '
            f'font-family:Courier New;">{_ipca_h:.1f}%</div>'
            f'</div>'

            f'<div style="text-align:center;">'
            f'<div style="font-size:0.65rem; color:#444; '
            f'text-transform:uppercase;">vix {_icone_vix}</div>'
            f'<div style="font-size:0.9rem; color:#ccc; '
            f'font-family:Courier New;">{_vix_h:.1f}</div>'
            f'</div>'

            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

# ── OPORTUNIDADES DO MOMENTO ─────────────────────────────────────────
_wl_home = listar_watchlist()
_tickers_wl_home = tuple([
    item['ticker'] for item in _wl_home
    if item.get('ticker')
])

if _tickers_wl_home:
    with st.spinner("identificando oportunidades..."):
        _opps = calcular_oportunidades_watchlist(_tickers_wl_home)

    if _opps:
        section_title("⚡ oportunidades do momento — sua watchlist")

        st.markdown(
            '<div style="font-family:Courier New; font-size:0.72rem; '
            'color:#555; margin-bottom:12px; line-height:1.6;">'
            'ativos com health score ≥ 55, momentum positivo recente '
            'e maior distância do topo de 52 semanas — '
            'maior assimetria risco/retorno no momento.'
            '</div>',
            unsafe_allow_html=True,
        )

        def _render_opp_card(_opp, _rank):
            _hs_opp = _opp['score_hs']
            _cor_hs = (
                "#00C853" if _hs_opp >= 65
                else "#FF9900" if _hs_opp >= 45
                else "#FF1744"
            )
            _cor_1m = "#00C853" if _opp['ret_1m'] >= 0 else "#FF1744"
            _cor_3m = "#00C853" if _opp['ret_3m'] >= 0 else "#FF1744"
            _badges = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            _badge  = _badges[_rank] if _rank < 5 else ""

            st.markdown(
                f'<div style="background:#0d0d0d; '
                f'border:1px solid #1e1e1e; '
                f'border-top:2px solid {_cor_hs}; '
                f'border-radius:6px; padding:16px; '
                f'height:100%;">'

                f'<div style="display:flex; justify-content:space-between; '
                f'align-items:center; margin-bottom:6px;">'
                f'<span style="font-family:Courier New; font-size:1rem; '
                f'font-weight:700; color:#FF9900;">'
                f'{_opp["ticker"].replace(".SA","")}</span>'
                f'<span style="font-size:1.1rem;">{_badge}</span>'
                f'</div>'

                f'<div style="font-family:Courier New; font-size:0.68rem; '
                f'color:#444; margin-bottom:12px; line-height:1.4;">'
                f'{_opp["nome"].lower()}<br>'
                f'{_opp["setor"][:30] if _opp["setor"] != "—" else ""}'
                f'</div>'

                f'<div style="display:flex; justify-content:space-between; '
                f'margin-bottom:6px;">'
                f'<span style="font-size:0.65rem; color:#555; '
                f'text-transform:uppercase;">health score</span>'
                f'<span style="font-family:Courier New; color:{_cor_hs}; '
                f'font-weight:700; font-size:0.9rem;">'
                f'{_hs_opp}/100</span>'
                f'</div>'

                f'<div style="display:flex; justify-content:space-between; '
                f'margin-bottom:4px;">'
                f'<span style="font-size:0.65rem; color:#555;">ret 1m</span>'
                f'<span style="font-family:Courier New; color:{_cor_1m}; '
                f'font-size:0.82rem;">{_opp["ret_1m"]:+.1f}%</span>'
                f'</div>'

                f'<div style="display:flex; justify-content:space-between; '
                f'margin-bottom:4px;">'
                f'<span style="font-size:0.65rem; color:#555;">ret 3m</span>'
                f'<span style="font-family:Courier New; color:{_cor_3m}; '
                f'font-size:0.82rem;">{_opp["ret_3m"]:+.1f}%</span>'
                f'</div>'

                f'<div style="display:flex; justify-content:space-between; '
                f'margin-bottom:12px;">'
                f'<span style="font-size:0.65rem; color:#555;">'
                f'dist. topo 52w</span>'
                f'<span style="font-family:Courier New; color:#888; '
                f'font-size:0.82rem;">{_opp["dist_top"]:.1f}%</span>'
                f'</div>'

                f'<div style="background:#111; border-radius:4px; '
                f'padding:6px 10px; text-align:center;">'
                f'<div style="font-size:0.6rem; color:#444; '
                f'text-transform:uppercase; margin-bottom:2px;">'
                f'score de assimetria</div>'
                f'<div style="font-family:Courier New; font-size:1rem; '
                f'color:#FF9900; font-weight:700;">'
                f'{_opp["score_assim"]:.0f}/100</div>'
                f'</div>'

                f'</div>',
                unsafe_allow_html=True,
            )

            st.markdown("<br style='margin:4px'>", unsafe_allow_html=True)
            _btn_key = f"btn_opp_research_{_opp['ticker']}_{_rank}"
            if st.button(
                f"🔬 analisar {_opp['ticker'].replace('.SA','')}",
                key=_btn_key,
                use_container_width=True,
            ):
                st.session_state['research_ticker_externo'] = _opp['ticker']
                st.switch_page("pages/1_Research.py")

        _opps_br  = [o for o in _opps if o.get('mercado') == 'BR']
        _opps_eua = [o for o in _opps if o.get('mercado') == 'EUA']

        if _opps_br:
            st.markdown(
                '<div style="font-family:Courier New; font-size:0.72rem; '
                'color:#555; margin:8px 0 4px 0;">🇧🇷 brasil</div>',
                unsafe_allow_html=True,
            )
            _cols_br = st.columns(min(len(_opps_br), 3))
            for _ci, (_col_opp, _opp) in enumerate(zip(_cols_br, _opps_br)):
                with _col_opp:
                    _render_opp_card(_opp, _ci)

        if _opps_eua:
            st.markdown(
                '<div style="font-family:Courier New; font-size:0.72rem; '
                'color:#555; margin:12px 0 4px 0;">🇺🇸 eua</div>',
                unsafe_allow_html=True,
            )
            _cols_eua = st.columns(min(len(_opps_eua), 3))
            for _ci, (_col_opp, _opp) in enumerate(zip(_cols_eua, _opps_eua)):
                with _col_opp:
                    _render_opp_card(_opp, _ci)

        st.markdown("<br>", unsafe_allow_html=True)

# ==========================================
# NAVEGAÇÃO RÁPIDA
# ==========================================
section_title("⚡ navegação rápida")

# CSS: page_link vira rodapé do card
st.markdown("""
<style>
[data-testid="stPageLink"] a {
    background: var(--bg-elevated) !important;
    border: 1px solid var(--border-subtle) !important;
    border-top: none !important;
    border-radius: 0 0 var(--radius-md) var(--radius-md) !important;
    display: block !important;
    padding: 6px 10px !important;
    text-align: center !important;
    text-decoration: none !important;
    transition: all 0.15s ease !important;
}
[data-testid="stPageLink"] a:hover {
    background: var(--bg-overlay) !important;
    border-color: var(--accent-border) !important;
}
[data-testid="stPageLink"] p {
    font-family: var(--font-ui) !important;
    font-size: 0.70rem !important;
    font-weight: 500 !important;
    color: var(--text-muted) !important;
    margin: 0 !important;
}
[data-testid="stPageLink"] a:hover p {
    color: var(--accent) !important;
}
[data-testid="stPageLink"] svg {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)

_nav_items = [
    ("pages/1_Research.py",       "📊", "Research",       "análise micro"),
    ("pages/2_Discovery.py",      "🎯", "Discovery",      "screener"),
    ("pages/3_Macro.py",          "🌍", "Macro",          "ambiente global"),
    ("pages/4_Portfolio.py",      "💼", "Portfólio",      "posições & P&L"),
    ("pages/5_Configuracoes.py",  "⚙️",  "Configurações",  "conta & preferências"),
]
_nav_cols = st.columns(5)
for _col, (_page, _icon, _titulo, _desc) in zip(_nav_cols, _nav_items):
    with _col:
        st.markdown(
            f'<div style="background:var(--bg-surface);'
            f' border:1px solid var(--border-subtle);'
            f' border-radius:var(--radius-md) var(--radius-md) 0 0;'
            f' padding:16px 10px 12px; text-align:center;">'
            f'<div style="font-size:1.5rem; margin-bottom:7px;">{_icon}</div>'
            f'<div style="font-family:var(--font-ui); font-size:0.82rem;'
            f' font-weight:600; color:var(--text-primary);">{_titulo}</div>'
            f'<div style="font-family:var(--font-ui); font-size:0.63rem;'
            f' color:var(--text-muted); margin-top:3px;">{_desc}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.page_link(_page, label="abrir →", use_container_width=True)

st.markdown("<div style='margin-bottom:12px;'></div>", unsafe_allow_html=True)

# ==========================================
# FAIXA 1 — PULSO DO MERCADO
# ==========================================
section_title("⚡ pulso do mercado")
auto_refresh_indicator(5)

@st.cache_data(ttl=300, show_spinner=False)
def buscar_indices_completo():
    tickers = {
        "ibovespa": "^BVSP",
        "s&p 500": "^GSPC",
        "nasdaq": "^IXIC",
        "dólar (brl)": "BRL=X",
        "bitcoin": "BTC-USD",
        "ouro": "GC=F",
        "vix": "^VIX",
        "treasury 10y": "^TNX",
    }
    resultados = {}
    try:
        hist = yf.download(list(tickers.values()), period="5d", auto_adjust=True, progress=False)['Close']
        for nome, tk in tickers.items():
            try:
                s = hist[tk].dropna() if isinstance(hist, pd.DataFrame) and tk in hist.columns else pd.Series()
                if len(s) >= 2:
                    preco = float(s.iloc[-1])
                    var = ((preco / float(s.iloc[-2])) - 1) * 100
                    resultados[nome] = {"preco": preco, "var": var, "ticker": tk}
            except:
                pass
    except:
        pass
    return resultados

def render_pulso_card(label: str, valor: str, var_pct: float):
    """Card de índice com badge-pill de variação colorido."""
    positivo = var_pct >= 0
    seta      = "▲" if positivo else "▼"
    cor_bg    = "rgba(16,185,129,0.10)"  if positivo else "rgba(239,68,68,0.10)"
    cor_borda = "rgba(16,185,129,0.25)"  if positivo else "rgba(239,68,68,0.25)"
    cor_txt   = "#10B981" if positivo else "#EF4444"
    st.markdown(
        f'<div style="background:var(--bg-surface);'
        f' border:1px solid var(--border-subtle);'
        f' border-radius:var(--radius-md);'
        f' padding:12px 14px; margin-bottom:6px;'
        f' transition:border-color 0.15s;">'
        f'<div style="font-family:var(--font-ui); font-size:0.62rem;'
        f' font-weight:600; color:var(--text-muted);'
        f' text-transform:uppercase; letter-spacing:0.08em;'
        f' margin-bottom:6px;">{label}</div>'
        f'<div style="font-family:var(--font-data); font-size:1.05rem;'
        f' font-weight:700; color:var(--text-primary);'
        f' line-height:1.2; margin-bottom:7px;">{valor}</div>'
        f'<span style="display:inline-flex; align-items:center;'
        f' gap:3px; padding:2px 8px; border-radius:20px;'
        f' background:{cor_bg}; border:1px solid {cor_borda};'
        f' font-family:var(--font-data); font-size:0.68rem;'
        f' font-weight:700; color:{cor_txt};">'
        f'{seta} {abs(var_pct):.2f}%</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

indices = buscar_indices_completo()
if indices:
    cols = st.columns(len(indices))
    for i, (nome, dados) in enumerate(indices.items()):
        tk = dados['ticker']
        if tk == "BRL=X":
            valor_fmt = f"R$ {dados['preco']:.4f}"
        elif tk in ["^VIX", "^TNX"]:
            valor_fmt = f"{dados['preco']:.2f}"
        elif tk == "GC=F":
            valor_fmt = f"$ {dados['preco']:,.2f}"
        elif tk == "BTC-USD":
            valor_fmt = f"$ {dados['preco']:,.0f}"
        else:
            valor_fmt = f"{dados['preco']:,.2f}"
        with cols[i]:
            render_pulso_card(nome, valor_fmt, dados['var'])

st.markdown("<br>", unsafe_allow_html=True)

# ==========================================
# FAIXA 2 — SEMÁFORO MACRO
# ==========================================
section_title("🚦 semáforo macro")

@st.cache_data(ttl=3600, show_spinner=False)
def buscar_dados_semaforo():
    dados = {
        "selic": None, "ipca": None,
        "t10y2y": None, "vix": None, "hy_spread": None,
        # fiscal BR
        "divida_pib": None, "tendencia_divida": None, "result_primario": None,
    }
    try:
        from fredapi import Fred
        fred = Fred(api_key=st.secrets["FRED_API_KEY"])
        t10y2y = fred.get_series('T10Y2Y', limit=1)
        if not t10y2y.empty:
            dados["t10y2y"] = float(t10y2y.iloc[-1])
        vix = fred.get_series('VIXCLS', limit=1)
        if not vix.empty:
            dados["vix"] = float(vix.iloc[-1])
        hy = fred.get_series('BAMLH0A0HYM2', limit=1)
        if not hy.empty:
            dados["hy_spread"] = float(hy.iloc[-1])
    except:
        pass
    try:
        from bcb import sgs
        selic_serie = sgs.get({'selic': 432}, last=1)
        if not selic_serie.empty:
            dados["selic"] = float(selic_serie['selic'].iloc[-1])
        ipca_serie = sgs.get({'ipca': 433}, last=1)
        if not ipca_serie.empty:
            dados["ipca"] = float(ipca_serie['ipca'].iloc[-1])
        # fiscal: dívida/PIB (últimos 7 pontos para calcular tendência 6 meses)
        divida_serie = sgs.get({'divida': 13762}, last=7)
        if not divida_serie.empty:
            dados["divida_pib"] = float(divida_serie['divida'].iloc[-1])
            if len(divida_serie) >= 7:
                dados["tendencia_divida"] = (
                    float(divida_serie['divida'].iloc[-1]) - float(divida_serie['divida'].iloc[0])
                )
        primario_serie = sgs.get({'primario': 5793}, last=1)
        if not primario_serie.empty:
            dados["result_primario"] = float(primario_serie['primario'].iloc[-1])
    except:
        pass
    return dados

dados_sem = buscar_dados_semaforo()

def avaliar_semaforo_brasil(selic, ipca):
    if selic is None: return "amber", "⚠️", "dados indisponíveis"
    if selic > 13: return "bear", "🔴", f"juro restritivo ({selic:.1f}%)"
    if selic > 10: return "amber", "🟡", f"juro elevado ({selic:.1f}%)"
    return "bull", "🟢", f"ambiente favorável ({selic:.1f}%)"

def avaliar_semaforo_eua(t10y2y, vix):
    if t10y2y is None or vix is None: return "amber", "⚠️", "dados indisponíveis"
    if t10y2y < -0.2 and vix > 25: return "bear", "🔴", "curva invertida + stress"
    if t10y2y < 0: return "amber", "🟡", f"curva invertida ({t10y2y:.2f}%)"
    if vix > 25: return "amber", "🟡", f"vix elevado ({vix:.1f})"
    return "bull", "🟢", f"spread positivo ({t10y2y:.2f}%)"

def avaliar_semaforo_risco(vix, hy_spread):
    if vix is None: return "amber", "⚠️", "dados indisponíveis"
    if vix > 30 or (hy_spread and hy_spread > 6): return "bear", "🔴", "stress elevado"
    if vix > 20 or (hy_spread and hy_spread > 4): return "amber", "🟡", f"atenção (vix {vix:.1f})"
    return "bull", "🟢", f"risco controlado (vix {vix:.1f})"

def avaliar_semaforo_fiscal(divida_pib, tendencia, primario):
    """Retorna (cor, icone, texto) para o card fiscal do semáforo da Home."""
    if divida_pib is None and primario is None:
        return "amber", "⚠️", "dados indisponíveis"
    pontos = 0
    if divida_pib is not None:
        if divida_pib > 90:   pontos += 3
        elif divida_pib > 80: pontos += 2
        elif divida_pib > 70: pontos += 1
    if tendencia is not None:
        if tendencia > 3:   pontos += 2
        elif tendencia > 1: pontos += 1
    if primario is not None:
        if primario < -3:   pontos += 2
        elif primario < -1: pontos += 1
    if pontos >= 5:
        return "bear",  "🔴", f"fiscal crítico (dívida {divida_pib:.0f}% pib)" if divida_pib else "fiscal crítico"
    if pontos >= 3:
        return "amber", "🟡", f"atenção fiscal (dívida {divida_pib:.0f}% pib)" if divida_pib else "atenção fiscal"
    return "bull", "🟢", f"fiscal estável (dívida {divida_pib:.0f}% pib)" if divida_pib else "fiscal estável"

def calcular_ambiente_macro(selic, vix, t10y2y, hy_spread,
                             fiscal_status=None) -> dict:
    """
    Consolida os indicadores macro em um score único 0-100.
    100 = ambiente ideal para risco / 0 = ambiente hostil, defensivo.
    """
    score  = 50  # neutro como base
    sinais = []

    # ── VIX (peso: 25pts) ───────────────────────────────────────────────────
    if vix is not None:
        if vix < 15:
            score += 12
            sinais.append(("VIX", "baixo", "bull", f"{vix:.1f}"))
        elif vix < 20:
            score += 5
            sinais.append(("VIX", "normal", "amber", f"{vix:.1f}"))
        elif vix < 30:
            score -= 8
            sinais.append(("VIX", "elevado", "amber", f"{vix:.1f}"))
        else:
            score -= 20
            sinais.append(("VIX", "crítico", "bear", f"{vix:.1f}"))

    # ── CURVA DE JUROS EUA T10Y2Y (peso: 20pts) ─────────────────────────────
    if t10y2y is not None:
        if t10y2y > 0.5:
            score += 10
            sinais.append(("Curva EUA", "normal", "bull", f"+{t10y2y:.2f}%"))
        elif t10y2y > 0:
            score += 3
            sinais.append(("Curva EUA", "achatada", "amber", f"+{t10y2y:.2f}%"))
        elif t10y2y > -0.5:
            score -= 8
            sinais.append(("Curva EUA", "invertida", "amber", f"{t10y2y:.2f}%"))
        else:
            score -= 18
            sinais.append(("Curva EUA", "inv. severa", "bear", f"{t10y2y:.2f}%"))

    # ── HY SPREAD (peso: 20pts) ──────────────────────────────────────────────
    if hy_spread is not None:
        if hy_spread < 3.5:
            score += 10
            sinais.append(("HY Spread", "comprimido", "bull", f"{hy_spread:.2f}%"))
        elif hy_spread < 5.0:
            score += 3
            sinais.append(("HY Spread", "normal", "amber", f"{hy_spread:.2f}%"))
        elif hy_spread < 7.0:
            score -= 8
            sinais.append(("HY Spread", "alargado", "amber", f"{hy_spread:.2f}%"))
        else:
            score -= 18
            sinais.append(("HY Spread", "crise crédito", "bear", f"{hy_spread:.2f}%"))

    # ── SELIC BR (peso: 15pts) ───────────────────────────────────────────────
    if selic is not None:
        if selic <= 9.0:
            score += 8
            sinais.append(("Selic", "favorável", "bull", f"{selic:.2f}%"))
        elif selic <= 11.0:
            score += 2
            sinais.append(("Selic", "neutra", "amber", f"{selic:.2f}%"))
        elif selic <= 13.0:
            score -= 5
            sinais.append(("Selic", "restritiva", "amber", f"{selic:.2f}%"))
        else:
            score -= 12
            sinais.append(("Selic", "muito restritiva", "bear", f"{selic:.2f}%"))

    # ── FISCAL BRASIL (peso: 10pts) ──────────────────────────────────────────
    if fiscal_status == 'critico':
        score -= 10
        sinais.append(("Fiscal BR", "crítico", "bear", "⚠️"))
    elif fiscal_status == 'alerta':
        score -= 4
        sinais.append(("Fiscal BR", "alerta", "amber", "⚠️"))
    elif fiscal_status == 'saudavel':
        score += 5
        sinais.append(("Fiscal BR", "estável", "bull", "✅"))

    score = min(max(int(score), 0), 100)

    if score >= 70:
        label = "RISK ON"
        cor   = "#00C853"
        tipo  = "bull"
        descr = ("ambiente favorável ao risco. indicadores macro "
                 "alinhados para ativos de crescimento.")
    elif score >= 50:
        label = "NEUTRO"
        cor   = "#FF9900"
        tipo  = "amber"
        descr = ("ambiente misto. seletividade é essencial. "
                 "prefira ativos de qualidade comprovada.")
    elif score >= 35:
        label = "CAUTELOSO"
        cor   = "#FF9900"
        tipo  = "amber"
        descr = ("sinais de alerta presentes. reduza exposição "
                 "especulativa e eleve qualidade da carteira.")
    else:
        label = "RISK OFF"
        cor   = "#FF1744"
        tipo  = "bear"
        descr = ("ambiente hostil ao risco. priorize caixa, "
                 "renda fixa curta e ativos defensivos.")

    return {
        'score':  score,
        'label':  label,
        'cor':    cor,
        'tipo':   tipo,
        'descr':  descr,
        'sinais': sinais,
    }


# ── determina status fiscal para o scoring ──────────────────────────────────
cor_fiscal, _, _ = avaliar_semaforo_fiscal(
    dados_sem.get("divida_pib"),
    dados_sem.get("tendencia_divida"),
    dados_sem.get("result_primario"),
)
_fiscal_map = {"bear": "critico", "amber": "alerta", "bull": "saudavel"}
fiscal_st_home = _fiscal_map.get(cor_fiscal)

ambiente = calcular_ambiente_macro(
    selic        = dados_sem.get('selic'),
    vix          = dados_sem.get('vix'),
    t10y2y       = dados_sem.get('t10y2y'),
    hy_spread    = dados_sem.get('hy_spread'),
    fiscal_status= fiscal_st_home,
)

# Persiste no session_state para outros módulos consumirem
st.session_state['macro_score']   = ambiente['score']
st.session_state['macro_label']   = ambiente['label']
st.session_state['selic']         = dados_sem.get('selic') or 10.75
st.session_state['macro_context'] = {
    'selic': dados_sem.get('selic') or 10.75,
    'vix':   dados_sem.get('vix')   or 15.0,
    'ipca':  dados_sem.get('ipca')  or 4.5,
}

# ── renderização: gauge + sinais individuais ─────────────────────────────────
col_gauge_mac, col_sinais_mac = st.columns([1, 2])

with col_gauge_mac:
    fig_mac = go.Figure(go.Indicator(
        mode  = "gauge+number",
        value = ambiente['score'],
        title = {
            'text': "ambiente macro",
            'font': {'color': '#555', 'family': 'Courier New', 'size': 12},
        },
        gauge = {
            'axis': {
                'range': [0, 100],
                'tickcolor': '#333',
                'tickfont': {'color': '#444', 'size': 9},
            },
            'bar': {'color': ambiente['cor'], 'thickness': 0.25},
            'bgcolor': '#13141E',
            'bordercolor': '#2A2C3E',
            'steps': [
                {'range': [0,  35],  'color': '#2a0a12'},
                {'range': [35, 50],  'color': '#2a1a00'},
                {'range': [50, 70],  'color': '#1C1D2B'},
                {'range': [70, 100], 'color': '#0a2218'},
            ],
            'threshold': {
                'line': {'color': ambiente['cor'], 'width': 3},
                'thickness': 0.8,
                'value': ambiente['score'],
            },
        },
        number = {
            'font': {'color': ambiente['cor'], 'family': 'Courier New', 'size': 42},
        },
    ))

    layout_mac = base_layout(height=230)
    layout_mac.update({
        'margin':       {'l': 10, 'r': 10, 't': 50, 'b': 10},
        'paper_bgcolor': '#13141E',
    })
    fig_mac.update_layout(**layout_mac)
    st.plotly_chart(fig_mac, use_container_width=True)

    st.markdown(
        f'<div style="text-align:center; font-family:Courier New; font-size:1.1rem; '
        f'color:{ambiente["cor"]}; font-weight:bold; margin-top:-16px; '
        f'letter-spacing:0.1em;">{ambiente["label"]}</div>',
        unsafe_allow_html=True,
    )

with col_sinais_mac:
    section_title("sinais individuais")

    for nome, status, tipo_s, valor in ambiente['sinais']:
        cor_s  = ("#00C853" if tipo_s == "bull" else
                  "#FF1744" if tipo_s == "bear" else "#FF9900")
        icone  = ("✅" if tipo_s == "bull" else
                  "🚨" if tipo_s == "bear" else "⚠️")
        st.markdown(
            f'<div style="display:flex; justify-content:space-between; align-items:center; '
            f'padding:6px 0; border-bottom:1px solid #111;">'
            f'<span style="font-family:Courier New; font-size:0.75rem; color:#555; '
            f'text-transform:uppercase; letter-spacing:0.06em;">{nome}</span>'
            f'<span style="font-family:Courier New; font-size:0.78rem; '
            f'color:{cor_s};">{icone} {status}</span>'
            f'<span style="font-family:Courier New; font-size:0.75rem; '
            f'color:#333;">{valor}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    status_card("leitura macro", ambiente['descr'], tipo=ambiente['tipo'])

st.markdown("<br>", unsafe_allow_html=True)

# ==========================================
# FAIXA 3 — PRÓXIMOS EVENTOS CRÍTICOS
# ==========================================
section_title("📅 próximos eventos")

import datetime as dt_module

@st.cache_data(ttl=3600, show_spinner=False)
def get_proximos_eventos_home():
    hoje = dt_module.date.today()
    eventos = [
        {"data": dt_module.date(2026, 5, 13), "evento": "CPI EUA", "categoria": "eua", "impacto": "alto"},
        {"data": dt_module.date(2026, 6, 5),  "evento": "Payroll EUA", "categoria": "eua", "impacto": "alto"},
        {"data": dt_module.date(2026, 6, 9),  "evento": "IPCA (IBGE)", "categoria": "brasil", "impacto": "medio"},
        {"data": dt_module.date(2026, 6, 10), "evento": "CPI EUA", "categoria": "eua", "impacto": "medio"},
        {"data": dt_module.date(2026, 6, 17), "evento": "COPOM — juros", "categoria": "brasil", "impacto": "alto"},
        {"data": dt_module.date(2026, 6, 17), "evento": "Fed — FOMC", "categoria": "eua", "impacto": "alto"},
        {"data": dt_module.date(2026, 7, 2),  "evento": "Payroll EUA", "categoria": "eua", "impacto": "alto"},
        {"data": dt_module.date(2026, 7, 9),  "evento": "IPCA (IBGE)", "categoria": "brasil", "impacto": "medio"},
        {"data": dt_module.date(2026, 7, 14), "evento": "CPI EUA", "categoria": "eua", "impacto": "medio"},
        {"data": dt_module.date(2026, 7, 29), "evento": "COPOM — juros", "categoria": "brasil", "impacto": "alto"},
        {"data": dt_module.date(2026, 7, 29), "evento": "Fed — FOMC", "categoria": "eua", "impacto": "alto"},
    ]
    proximos = sorted([e for e in eventos if e['data'] >= hoje], key=lambda x: x['data'])
    return proximos[:4]

proximos_eventos = get_proximos_eventos_home()
if proximos_eventos:
    ev_cols = st.columns(len(proximos_eventos))
    hoje_home = dt_module.date.today()
    for i, ev in enumerate(proximos_eventos):
        dias = (ev['data'] - hoje_home).days
        cor_cat = {"brasil": "#009C3B", "eua": "#3C3B6E"}.get(ev['categoria'], "#555")
        cor_dias = "#FF1744" if dias <= 3 else ("#FF9900" if dias <= 7 else "#555")
        icone_imp = "🔴" if ev['impacto'] == 'alto' else "🟡"
        with ev_cols[i]:
            st.markdown(f'''<div style="background:#0d0d0d; border:1px solid #1e1e1e; border-top:2px solid {cor_cat}; border-radius:6px; padding:12px; text-align:center;">
            <div style="font-family:Courier New; font-size:0.68rem; color:{cor_cat}; text-transform:uppercase; font-weight:bold;">{ev['categoria']}</div>
            <div style="font-family:Courier New; font-size:0.85rem; color:#E0E0E0; margin:6px 0;">{icone_imp} {ev['evento']}</div>
            <div style="font-family:Courier New; font-size:0.75rem; color:{cor_dias};">{ev['data'].strftime('%d/%m/%Y')}</div>
            <div style="font-family:Courier New; font-size:0.68rem; color:#555; margin-top:2px;">em {dias} dias</div>
            </div>''', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ==========================================
# FAIXA 4 — RESUMO DO PORTFÓLIO + WATCHLIST HIGHLIGHTS
# ==========================================
pesos_atuais = get_pesos()
ativos_alocados = {p['ticker']: p for p in pesos_atuais if p['peso'] > 0}

if ativos_alocados:
    section_title("💼 portfólio & watchlist highlights")

    tickers_com_peso = list(ativos_alocados.keys())
    with st.spinner("sincronizando..."):
        live_data_port = {}
        var_dia_port = {}
        try:
            tickers_base_port = list(set([mapear_ticker_base(t) for t in tickers_com_peso]))
            hist_port = yf.download(tickers_base_port, period="5d", auto_adjust=True, progress=False)['Close']
            if isinstance(hist_port, pd.Series):
                hist_port = hist_port.to_frame(name=tickers_base_port[0])
            hist_port = hist_port.ffill()
            for t in tickers_com_peso:
                t_base = mapear_ticker_base(t)
                try:
                    s = hist_port[t_base].dropna()
                    if len(s) >= 2:
                        live_data_port[t] = float(s.iloc[-1])
                        var_dia_port[t] = ((float(s.iloc[-1]) / float(s.iloc[-2])) - 1) * 100
                except:
                    live_data_port[t] = 0.0
        except:
            pass

    custo_total = sum(float(d.get('quantidade',0)) * float(d.get('preco_medio',0)) for d in ativos_alocados.values())
    valor_atual = sum(float(d.get('quantidade',0)) * live_data_port.get(t,0) for t, d in ativos_alocados.items())
    pnl_valor = valor_atual - custo_total
    pnl_pct = (pnl_valor / custo_total * 100) if custo_total > 0 else 0

    pf1, pf2, pf3, pf4 = st.columns(4)
    with pf1: metric_card("patrimônio atual", fmt_preco(valor_atual, "$"), fmt_pct(pnl_pct), "bull" if pnl_pct >= 0 else "bear")
    with pf2: metric_card("p&l total", fmt_preco(pnl_valor, "$"), "", "bull" if pnl_valor >= 0 else "bear")

    if var_dia_port:
        melhor_t = max(var_dia_port, key=var_dia_port.get)
        pior_t = min(var_dia_port, key=var_dia_port.get)
        with pf3: metric_card("melhor hoje", melhor_t, fmt_pct(var_dia_port[melhor_t]), "bull")
        with pf4: metric_card("pior hoje", pior_t, fmt_pct(var_dia_port[pior_t]), "bear")

    st.markdown("<br>", unsafe_allow_html=True)

    health_data_home = {h['ticker']: h for h in get_health_scores()}
    ativos_alerta = []
    for t in tickers_com_peso:
        t_base = mapear_ticker_base(t)
        h = health_data_home.get(t_base, {})
        score = h.get('score', 50)
        if score < 40:
            ativos_alerta.append((t, score))

    if ativos_alerta:
        alertas_txt = " | ".join([f"{t} ({s:.0f})" for t, s in sorted(ativos_alerta, key=lambda x: x[1])[:3]])
        st.warning(f"🚨 atenção no portfólio — health score crítico: {alertas_txt}")

    st.caption("🔍 para análise completa acesse meu portfólio.")
    st.markdown("---")

# ==========================================
# WATCHLIST INTELIGENTE E SELETOR
# ==========================================
section_title("👁️ watchlist & radar de alertas")

watchlists_disponiveis = listar_watchlists()
if not watchlists_disponiveis:
    get_watchlist_padrao()
    watchlists_disponiveis = listar_watchlists()

if 'watchlist_ativa_id' not in st.session_state:
    st.session_state['watchlist_ativa_id'] = watchlists_disponiveis[0]['id']

opcoes_wl = {f"{wl['icone']} {wl['nome']} ({wl['total_ativos']} ativos)": wl['id'] for wl in watchlists_disponiveis}

idx_ativo = 0
for i, wl in enumerate(watchlists_disponiveis):
    if wl['id'] == st.session_state['watchlist_ativa_id']:
        idx_ativo = i
        break

col_sel_wl, col_btn_nova, col_btn_cfg = st.columns([5, 2, 1])

with col_sel_wl:
    sel_wl_label = st.selectbox("watchlist ativa:", list(opcoes_wl.keys()), index=idx_ativo, key="sel_watchlist_ativa_ui", label_visibility="collapsed")
    st.session_state['watchlist_ativa_id'] = opcoes_wl[sel_wl_label]
    watchlist_id_ativo = st.session_state['watchlist_ativa_id']

with col_btn_nova:
    if st.button("➕ nova watchlist", use_container_width=True):
        st.session_state['criar_wl_modal'] = True

with col_btn_cfg:
    if st.button("⚙️", use_container_width=True, help="configurar watchlist"):
        st.session_state['cfg_wl_modal'] = True

# ── MODAIS DA WATCHLIST ───────────────────────
@st.dialog("➕ criar nova watchlist")
def modal_criar_watchlist():
    icones_opcoes = ["⭐","📈","🎯","💰","🏦","🌍","⚡","🔬","💼","🛡️"]
    cores_opcoes = {"âmbar (padrão)": "#FF9900", "verde": "#00C853", "azul": "#00B0FF", "vermelho": "#FF1744", "roxo": "#E040FB"}

    c1, c2 = st.columns([3, 1])
    with c1:
        nome_nova = st.text_input("nome:", placeholder="ex: dividendos br")
    with c2:
        icone_nova = st.selectbox("ícone:", icones_opcoes)

    descricao_nova = st.text_input("descrição (opcional):", placeholder="ex: ações de alta renda")
    cor_label = st.selectbox("cor:", list(cores_opcoes.keys()))
    cor_nova = cores_opcoes[cor_label]

    c_ok, c_cancel = st.columns(2)
    if c_ok.button("criar", type="primary", use_container_width=True):
        if nome_nova.strip():
            novo_id = criar_watchlist(nome_nova.strip(), descricao_nova, cor_nova, icone_nova)
            st.session_state['watchlist_ativa_id'] = novo_id
            st.success(f"{icone_nova} watchlist '{nome_nova.lower()}' criada!")
            time.sleep(1)
            st.rerun()
        else:
            st.warning("digite um nome.")
    if c_cancel.button("cancelar", use_container_width=True):
        st.rerun()

if st.session_state.get('criar_wl_modal'):
    st.session_state.pop('criar_wl_modal')
    modal_criar_watchlist()

@st.dialog("⚙️ configurar watchlist")
def modal_cfg_watchlist():
    wl_atual = next((wl for wl in watchlists_disponiveis if wl['id'] == watchlist_id_ativo), None)
    if not wl_atual:
        st.rerun()
        return

    st.markdown(f"**editando:** {wl_atual['icone']} {wl_atual['nome']}")

    icones_opcoes = ["⭐","📈","🎯","💰","🏦","🌍","⚡","🔬","💼","🛡️"]
    novo_nome = st.text_input("nome:", value=wl_atual['nome'])
    nova_desc = st.text_input("descrição:", value=wl_atual.get('descricao',''))
    novo_icone = st.selectbox("ícone:", icones_opcoes, index=icones_opcoes.index(wl_atual.get('icone','⭐')) if wl_atual.get('icone','⭐') in icones_opcoes else 0)

    col_a, col_b, col_c = st.columns(3)
    if col_a.button("💾 salvar", type="primary", use_container_width=True):
        renomear_watchlist(watchlist_id_ativo, novo_nome, nova_desc, novo_icone)
        st.success("watchlist atualizada!")
        time.sleep(1)
        st.rerun()

    if col_b.button("⭐ definir padrão", use_container_width=True):
        definir_watchlist_padrao(watchlist_id_ativo)
        st.success("definida como padrão!")
        time.sleep(1)
        st.rerun()

    pode_deletar = len(watchlists_disponiveis) > 1
    if col_c.button("🗑️ deletar", use_container_width=True, disabled=not pode_deletar, help="deleta a watchlist e todos os ativos nela"):
        deletar_watchlist(watchlist_id_ativo)
        st.session_state['watchlist_ativa_id'] = watchlists_disponiveis[0]['id']
        st.success("watchlist deletada.")
        time.sleep(1)
        st.rerun()

if st.session_state.get('cfg_wl_modal'):
    st.session_state.pop('cfg_wl_modal')
    modal_cfg_watchlist()

# ── BUSCAR E ADICIONAR ATIVO ──
expandir_busca = bool(st.session_state.get('resultados_busca'))

with st.expander("🔍 buscar e adicionar novo ativo", expanded=expandir_busca):
    with st.form("form_busca_ativo", clear_on_submit=False):
        c1, c2 = st.columns([4, 1])
        with c1:
            termo = st.text_input("digite o nome da empresa ou ativo:", key="input_busca", label_visibility="collapsed", placeholder="buscar ativo (ex: aapl, wege3)...")
        with c2:
            btn_buscar = st.form_submit_button("buscar", use_container_width=True, type="primary")
            
    if btn_buscar and termo:
        with st.spinner("procurando na api global..."):
            resultados = buscar_ativo_yahoo(termo)
            st.session_state['resultados_busca'] = resultados
            if not resultados:
                st.warning("nenhum ativo encontrado.")
                
    if st.session_state.get('resultados_busca'):
        opcoes_formatadas = []
        ativos_validos = []
        for q in st.session_state['resultados_busca']:
            tk = q.get('symbol'); nm = q.get('shortname') or q.get('longname')
            if tk and nm:
                bolsa = q.get('exchDisp', 'desconhecida')
                opcoes_formatadas.append(f"{tk} | {nm.lower()} ({bolsa.lower()})")
                ativos_validos.append(q)
        
        if opcoes_formatadas:
            st.markdown("---")
            cs1, cs2, cs3 = st.columns([4, 3, 2])
            with cs1:
                escolha = st.selectbox("selecione o ativo correto:", opcoes_formatadas, label_visibility="collapsed", key="busca_ativo_correto")
                idx = opcoes_formatadas.index(escolha)
                ativo_escolhido = ativos_validos[idx]
            with cs2:
                opcoes_destino = {f"{wl['icone']} {wl['nome']}": wl['id'] for wl in watchlists_disponiveis}
                idx_dest = list(opcoes_destino.values()).index(watchlist_id_ativo) if watchlist_id_ativo in opcoes_destino.values() else 0
                destino_wl_nome = st.selectbox("adicionar à:", list(opcoes_destino.keys()), index=idx_dest, label_visibility="collapsed", key="busca_destino_wl")
                destino_wl_id = opcoes_destino[destino_wl_nome]
            with cs3:
                if st.button("salvar na watchlist", type="primary", use_container_width=True, key="btn_salvar_novo_ativo"):
                    tk = ativo_escolhido['symbol']
                    nm = ativo_escolhido.get('shortname') or ativo_escolhido.get('longname', tk)
                    bolsa_str = ativo_escolhido.get('exchDisp', '').lower()
                    tipo_str = ativo_escolhido.get('quoteType', '').lower()
                    
                    if "são paulo" in bolsa_str or tk.endswith(".SA"): mercado = "brasil"
                    elif "nyse" in bolsa_str or "nasdaq" in bolsa_str: mercado = "eua"
                    elif "cryptocurrency" in tipo_str: mercado = "criptomoedas"
                    else: mercado = "outros"
                    
                    adicionar_ativo(tk, nm, mercado, watchlist_id=destino_wl_id)
                    st.success(f"{tk.lower()} adicionado!")
                    st.session_state['resultados_busca'] = []
                    time.sleep(1)
                    st.rerun()

st.markdown("<br>", unsafe_allow_html=True)

# ── ATUALIZAR SCORES ───────────────────────
col_btn, _ = st.columns([2, 8])
if col_btn.button("🚨 atualizar scores", use_container_width=True, type="primary"):
    ativos_atuais = listar_watchlist(watchlist_id=watchlist_id_ativo)
    if ativos_atuais:
        progress_steps(["inicializando", "coletando dados", "calculando scores"], current=1)
        barra = st.progress(0)
        txt = st.empty()
        total = len(ativos_atuais)
        
        # LOOP LIMPO DE VELOCIDADE MÁXIMA
        for idx, item in enumerate(ativos_atuais):
            t = item['ticker']
            txt.caption(f"a analisar {t.lower()}...")
            
            calcular_health_score(mapear_ticker_base(t))
            
            barra.progress((idx + 1) / total)
            
        txt.empty()
        barra.empty()
        progress_steps(["inicializando", "coletando dados", "calculando scores"], current=3)
        time.sleep(1) # pausa de UI (interface) rápida só pra mostrar "concluído" antes de sumir
        st.rerun()

# ── FUNÇÃO MODAL DO MEMORIAL ───────────────────────
@st.dialog("🧮 memorial de cálculo")
def exibir_memorial(ticker_nome, score_final, breakdown_dict, alertas_lista):
    import re as _re

    st.markdown(f"#### ativo: {ticker_nome.lower()}")

    cor_score = "#00C853" if score_final >= 65 else ("#FF9900" if score_final >= 40 else "#FF1744")
    st.markdown(
        f"<div style='font-size:2rem; font-family:Courier New; font-weight:bold; "
        f"color:{cor_score}; text-align:center; padding:10px; background:#111; "
        f"border-radius:8px; margin-bottom:20px;'>{score_final:.0f} / 100</div>",
        unsafe_allow_html=True,
    )

    if breakdown_dict:
        st.markdown("**🧱 pilares de pontuação:**")

        for pilar, v in breakdown_dict.items():
            # ── Extrai número da forma mais robusta possível ──────────────
            # v pode ser int, float ou string como "+6 pts", "12.5%", "n/d"
            pts_num = None
            if isinstance(v, (int, float)):
                pts_num = float(v)
            elif isinstance(v, str):
                m = _re.search(r'([+-]?\d+\.?\d*)', str(v))
                if m:
                    try:
                        pts_num = float(m.group(1))
                    except Exception:
                        pts_num = None

            # Decide se é pilar de pontuação (numérico inteiro/float direto)
            # ou dado informativo (string percentual, ratio, etc.)
            eh_pilar = isinstance(v, (int, float))

            if eh_pilar and pts_num is not None:
                # Pula penalidades zeradas para não poluir
                if pts_num == 0 and "penalidade" in pilar.lower():
                    continue
                cor_pts = "#00C853" if pts_num > 0 else ("#FF1744" if pts_num < 0 else "#666")
                sinal   = "+" if pts_num > 0 else ""
                st.markdown(
                    f"<div style='display:flex; justify-content:space-between; "
                    f"border-bottom:1px solid #222; padding:4px 0;'>"
                    f"<span style='color:#ccc;'>{pilar.lower()}</span> "
                    f"<span style='color:{cor_pts}; font-family:Courier New; font-weight:bold;'>"
                    f"{sinal}{pts_num:.0f} pts</span></div>",
                    unsafe_allow_html=True,
                )
            elif isinstance(v, str) and v not in ('n/d', '—', 'None', '', 'nan'):
                # Dado informativo: mostra em cinza mais claro
                cor_v = "#00C853" if v.startswith('+') else ("#FF1744" if v.startswith('-') else "#555")
                st.markdown(
                    f"<div style='display:flex; justify-content:space-between; "
                    f"padding:3px 0; font-family:Courier New; font-size:0.72rem;'>"
                    f"<span style='color:#444;'>{pilar.lower()}</span>"
                    f"<span style='color:{cor_v};'>{v}</span></div>",
                    unsafe_allow_html=True,
                )
    else:
        st.info("💡 memorial não disponível. clique em '🚨 atualizar health scores' no topo da página para recalcular este ativo na nova versão.")

    if alertas_lista:
        st.markdown("<br>**🚨 contexto & alertas:**", unsafe_allow_html=True)
        for a in alertas_lista:
            st.markdown(
                f"<div style='font-size:0.8rem; color:#aaa; margin-bottom:4px; "
                f"padding-left:10px; border-left:2px solid #444;'>{a}</div>",
                unsafe_allow_html=True,
            )

# ── GRID DA WATCHLIST ATIVA ─────────────────────────────
watchlist = listar_watchlist(watchlist_id=watchlist_id_ativo)

# Onboarding: intercepta quando watchlist está vazia E é primeiro acesso
_user_home = get_current_user()
if (not watchlist
        and _user_home
        and is_primeiro_acesso(_user_home['user_id'])
        and not st.session_state.get('skip_onboarding')):
    from utils.onboarding import render_onboarding
    render_onboarding(_user_home['user_id'], watchlist_id_ativo)
    st.markdown("---")
    if st.button("pular onboarding e ir direto →", key="btn_skip_ob"):
        st.session_state['skip_onboarding'] = True
        st.rerun()
    st.stop()

if not watchlist:
    empty_state(icone="⭐", titulo="watchlist vazia", descricao="a sua lista de monitorização está vazia. utilize a barra de pesquisa acima para adicionar ativos.")
else:
    tickers_ativos = [item['ticker'] for item in watchlist]
    live_data = {}
    health_data = {h['ticker']: h for h in get_health_scores()}

    with st.spinner("sincronizando cotações em tempo real..."):
        try:
            tickers_base = list(set([mapear_ticker_base(t) for t in tickers_ativos]))
            data = yf.download(tickers_base, period="1mo", auto_adjust=True, progress=False)
            
            if not data.empty and 'Close' in data.columns:
                hist = data['Close']
                if isinstance(hist, pd.Series): 
                    hist = hist.to_frame(name=tickers_base[0])
                hist = hist.ffill()
                
                for t in tickers_ativos:
                    t_base = mapear_ticker_base(t)
                    try:
                        if t_base in hist.columns:
                            s = hist[t_base].dropna()
                            if len(s) >= 2:
                                p_atual = float(s.iloc[-1])
                                p_ontem = float(s.iloc[-2])
                                p_1m = float(s.iloc[0])
                                live_data[t] = {'preco': p_atual, 'var_1d': ((p_atual/p_ontem)-1)*100, 'var_1m': ((p_atual/p_1m)-1)*100}
                    except:
                        pass
        except:
            pass

    # ── Complementa com cotações em lote (cache de 5min) ─────────────────
    _tickers_cot = tuple([item['ticker'] for item in watchlist if item.get('ticker')])
    _cotacoes = buscar_cotacoes_lote(_tickers_cot) if _tickers_cot else {}
    for _tk_cot, _d_cot in _cotacoes.items():
        if _tk_cot not in live_data or live_data[_tk_cot].get('preco', 0) == 0:
            live_data[_tk_cot] = _d_cot

    # Earnings próximos (próximos 14 dias)
    _earnings_prox = buscar_earnings_proximos(_tickers_cot) if _tickers_cot else {}

    # ── Busca datas de earnings para os cards da watchlist ───────────────────
    import datetime as _dt_mod
    _hoje_home       = _dt_mod.date.today()
    _tickers_base_wl = list(set(
        mapear_ticker_base(i['ticker'])
        for i in watchlist
        if i.get('ticker')
    ))

    # 1. Tenta pegar do cache Supabase primeiro (1 round-trip para N tickers)
    _earnings_cache: dict = get_earnings_dates(_tickers_base_wl)

    # 2. Para tickers sem cache, busca via scraper e persiste
    #    (só roda para não-FIIs; falha silenciosa se tabela não existir)
    _sem_cache = [_tb for _tb in _tickers_base_wl
                  if _tb not in _earnings_cache and not _is_fii(_tb)]
    if _sem_cache:
        with st.spinner("buscando datas de resultados..."):
            for _tb in _sem_cache:
                try:
                    _earn_d = buscar_resultados(_tb)
                    _prox   = _earn_d.get('proxima_data')
                    # Persiste no Supabase (ignora erro se tabela não existir)
                    try:
                        salvar_earnings_date(_tb, _prox, _earn_d.get('fonte', ''))
                    except Exception:
                        pass
                    # Sempre atualiza o cache em memória
                    if _prox:
                        try:
                            _earnings_cache[_tb] = _dt_mod.datetime.strptime(
                                _prox, '%d/%m/%Y'
                            ).date()
                        except Exception:
                            pass
                except Exception:
                    pass

    # 3. Monta mapa {ticker_base: earnings_info} para os cards (janela -1 a +14 dias)
    _earnings_info_map: dict = {}
    for _tb, _dt_earn in _earnings_cache.items():
        try:
            _dias = (_dt_earn - _hoje_home).days
            if -1 <= _dias <= 14:
                _earnings_info_map[_tb] = {
                    'dias': _dias,
                    'data': _dt_earn.strftime('%d/%m/%Y'),
                }
        except Exception:
            pass

    # Merge earnings_prox no info_map (complementa tickers sem cache)
    for _ep_tk, _ep_dias in _earnings_prox.items():
        _ep_base = mapear_ticker_base(_ep_tk)
        if _ep_base not in _earnings_info_map:
            _earnings_info_map[_ep_base] = {
                'dias': _ep_dias,
                'data': '—',
            }

    # ── FILTRO POR TAG / TESE ────────────────────────────────────────────────
    tags_disponiveis = listar_tags_watchlist(watchlist_id_ativo)
    opcoes_filtro    = ['todas'] + tags_disponiveis

    col_tag1, col_tag2, col_tag3 = st.columns([3, 1, 1])
    with col_tag1:
        tag_filtro = st.radio(
            "filtrar por tese:",
            options=opcoes_filtro,
            format_func=lambda x: "🌐 todas" if x == 'todas' else f"📁 {x}",
            horizontal=True,
            key="wl_tag_filtro",
            label_visibility="collapsed",
        )
    with col_tag2:
        if st.button("🏷️ editar tags", key="btn_editar_tags", use_container_width=True):
            st.session_state['modo_editar_tags'] = not st.session_state.get('modo_editar_tags', False)
    with col_tag3:
        _n_grupos = len(tags_disponiveis) if tags_disponiveis else 1
        st.markdown(
            f'<div style="font-family:Courier New; font-size:0.75rem; color:#555; '
            f'padding-top:8px; text-align:right;">'
            f'{len(watchlist)} ativos | {_n_grupos} grupo{"s" if _n_grupos != 1 else ""}</div>',
            unsafe_allow_html=True,
        )

    # Filtra watchlist pela tag selecionada
    if tag_filtro != 'todas':
        watchlist_filtrada = [i for i in watchlist if (i.get('tag') or 'geral') == tag_filtro]
    else:
        watchlist_filtrada = watchlist

    # Modo de edição de tags
    if st.session_state.get('modo_editar_tags'):
        with st.expander("🏷️ gerenciar tags dos ativos", expanded=True):
            st.markdown(
                '<div style="font-family:Courier New; font-size:0.75rem; color:#555; margin-bottom:12px;">'
                'organize seus ativos por tese de investimento. '
                'ex: <code>dividendos br</code>, <code>tech eua</code>, <code>fiis logística</code></div>',
                unsafe_allow_html=True,
            )

            _tags_sugeridas = [
                'dividendos br', 'tech eua', 'fiis logística',
                'fiis shoppings', 'fiis papel', 'blue chips',
                'small caps', 'tokenizados', 'commodities',
                'defensivo', 'especulativo',
            ]
            st.markdown(
                '<div style="font-family:Courier New; font-size:0.68rem; color:#444; margin-bottom:10px;">'
                'sugeridas: ' +
                ' | '.join(f'<code>{_t}</code>' for _t in _tags_sugeridas[:6]) +
                '</div>',
                unsafe_allow_html=True,
            )

            _cols_tag = st.columns(3)
            _changes: dict[str, str] = {}
            for _i, _item in enumerate(watchlist):
                _tk = _item['ticker']
                with _cols_tag[_i % 3]:
                    _nova_tag = st.text_input(
                        _tk.replace('.SA', ''),
                        value=_item.get('tag') or 'geral',
                        key=f"tag_edit_{_tk}",
                        placeholder="ex: dividendos br",
                    )
                    _changes[_tk] = _nova_tag

            _cs, _cc = st.columns(2)
            with _cs:
                if st.button("💾 salvar tags", type="primary", use_container_width=True, key="btn_salvar_tags"):
                    for _ticker_t, _tag_t in _changes.items():
                        if _tag_t.strip():
                            atualizar_tag_ativo(watchlist_id_ativo, _ticker_t, _tag_t)
                    st.success("✅ tags salvas!")
                    st.session_state['modo_editar_tags'] = False
                    st.rerun()
            with _cc:
                if st.button("cancelar", type="secondary", use_container_width=True, key="btn_cancel_tags"):
                    st.session_state['modo_editar_tags'] = False
                    st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # ── LISTA DENSA (usa watchlist_filtrada) ─────────────────────────────────
    mercados_dict = {}
    for item in watchlist_filtrada:
        m = item.get('mercado', 'outros').lower()
        mercados_dict.setdefault(m, []).append(item)

    if not mercados_dict:
        empty_state("🔍", f"sem ativos com tag '{tag_filtro}'",
                    "nenhum ativo encontrado para este filtro. edite as tags acima.")

    for mercado, ativos in mercados_dict.items():
        # Header do grupo de mercado
        st.markdown(
            f'<div style="font-family:Courier New;'
            f' font-size:0.60rem; font-weight:bold;'
            f' color:var(--text-muted); text-transform:uppercase;'
            f' letter-spacing:0.14em; padding:8px 0 4px;">'
            f'▸ {mercado}</div>',
            unsafe_allow_html=True,
        )

        # Header das colunas (uma vez por grupo)
        watchlist_header_row()

        for item in ativos:
            t      = item['ticker']
            t_base = mapear_ticker_base(t)
            d      = live_data.get(t, {'preco': 0.0, 'var_1d': 0.0, 'var_1m': 0.0})
            h_info = health_data.get(t_base, {'score': 50, 'alertas_venda': '{"alertas":[],"breakdown":{}}'})

            # Decodificação robusta
            try:
                raw_data    = h_info['alertas_venda']
                parsed_data = json.loads(raw_data)
                if isinstance(parsed_data, str):
                    parsed_data = json.loads(parsed_data)
                if isinstance(parsed_data, dict):
                    lista_alertas = parsed_data.get('alertas', [])
                    breakdown     = parsed_data.get('breakdown', {})
                else:
                    lista_alertas = parsed_data if isinstance(parsed_data, list) else []
                    breakdown     = {}
            except Exception:
                lista_alertas = []
                breakdown     = {}

            # Checkbox de seleção para comparativo
            _chk_key = f"chk_comp_{t}"
            _selecionado = st.checkbox("", key=_chk_key, label_visibility="collapsed")
            if _selecionado:
                _sel_list = st.session_state.get('comp_selecionados', [])
                if t not in _sel_list:
                    _sel_list.append(t)
                    st.session_state['comp_selecionados'] = _sel_list
            else:
                _sel_list = st.session_state.get('comp_selecionados', [])
                if t in _sel_list:
                    _sel_list.remove(t)
                    st.session_state['comp_selecionados'] = _sel_list

            watchlist_row(
                ticker        = t,
                nome          = item.get('nome', t),
                preco         = d.get('preco', 0.0),
                var_1d        = d.get('var_1d', 0.0),
                var_1m        = d.get('var_1m', 0.0),
                moeda         = "R$" if t_base.endswith(".SA") else "$",
                health_score  = h_info.get('score'),
                alertas       = lista_alertas,
                earnings_info = _earnings_info_map.get(t_base),
            )

            # Confirmação de deleção
            if st.session_state.get(f"confirm_del_{t}"):
                st.warning(f"remover {t.replace('.SA', '')} da watchlist?")
                c1, c2 = st.columns([1, 3])
                with c1:
                    if st.button("confirmar", type="primary", key=f"conf_del_{t}"):
                        remover_ativo(t, watchlist_id=watchlist_id_ativo)
                        st.session_state.pop(f"confirm_del_{t}", None)
                        st.rerun()
                with c2:
                    if st.button("cancelar", key=f"canc_del_{t}"):
                        st.session_state.pop(f"confirm_del_{t}", None)
                        st.rerun()

            # Memorial de cálculo
            if st.session_state.get(f"show_memorial_{t}"):
                exibir_memorial(t, h_info.get('score', 0), breakdown, lista_alertas)
                if st.button("fechar", key=f"close_mem_{t}"):
                    st.session_state.pop(f"show_memorial_{t}", None)
                    st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

    # ── Botão de comparar ativos selecionados ──────────────────────────────
    _selecionados_comp = st.session_state.get('comp_selecionados', [])
    if len(_selecionados_comp) >= 2:
        if st.button(
            f"⚖️ comparar selecionados "
            f"({', '.join([t.replace('.SA','') for t in _selecionados_comp])})",
            type="primary",
            use_container_width=True,
            key="btn_ir_comparativo",
        ):
            st.session_state['comp_ativos_presel'] = _selecionados_comp
            st.session_state['research_modo'] = 'Comparativo (Múltiplos)'
            st.session_state['comp_selecionados'] = []
            st.switch_page("pages/1_Research.py")
    elif len(_selecionados_comp) == 1:
        st.caption(
            f"selecione mais 1 ativo para comparar com "
            f"{_selecionados_comp[0].replace('.SA','')}"
        )

# ==========================================
# RELATÓRIO SEMANAL
# ==========================================
section_title("📧 relatório semanal")

ultimo_envio = get_ultimo_envio_relatorio()

col_rel1, col_rel2 = st.columns([3, 1])
with col_rel1:
    if ultimo_envio:
        from datetime import datetime
        dt_ultimo = datetime.fromisoformat(ultimo_envio['enviado_em'])
        dias_desde = (datetime.now() - dt_ultimo).days
        if dias_desde >= 7:
            st.info(f"📬 último relatório enviado há {dias_desde} dias ({dt_ultimo.strftime('%d/%m/%Y')}). hora de enviar o novo!")
        else:
            st.success(f"✅ relatório enviado em {dt_ultimo.strftime('%d/%m/%Y %H:%M')} — {dias_desde} dia(s) atrás.")
    else:
        st.info("📭 nenhum relatório enviado ainda. clique para gerar o primeiro.")

with col_rel2:
    btn_relatorio = st.button(
        "📧 enviar relatório",
        type="primary",
        use_container_width=True,
        key="btn_enviar_relatorio"
    )

if btn_relatorio:
    with st.spinner("montando relatório do portfólio..."):
        try:
            pesos_rel = get_pesos()
            ativos_rel = {p['ticker']: p for p in pesos_rel if p.get('quantidade', 0) > 0}

            if not ativos_rel:
                st.warning("nenhum ativo no portfólio para incluir no relatório.")
            else:
                health_rel = {h['ticker']: h for h in get_health_scores()}

                tickers_base_rel = list(set([mapear_ticker_base(t) for t in ativos_rel.keys()]))
                hist_rel = yf.download(tickers_base_rel, period="35d", auto_adjust=True, progress=False)['Close']
                if isinstance(hist_rel, pd.Series):
                    hist_rel = hist_rel.to_frame(name=tickers_base_rel[0])
                hist_rel = hist_rel.ffill()

                dados_carteira = []
                for t, dados in ativos_rel.items():
                    t_base = mapear_ticker_base(t)
                    score = health_rel.get(t_base, {}).get('score', 50)

                    var_1d = 0.0
                    var_1m = 0.0
                    try:
                        if t_base in hist_rel.columns:
                            s = hist_rel[t_base].dropna()
                            if len(s) >= 2:
                                var_1d = ((float(s.iloc[-1]) / float(s.iloc[-2])) - 1) * 100
                            if len(s) >= 22:
                                var_1m = ((float(s.iloc[-1]) / float(s.iloc[-22])) - 1) * 100
                    except:
                        pass

                    dados_carteira.append({
                        'ticker': t,
                        'score': score,
                        'var_1d': var_1d,
                        'var_1m': var_1m,
                    })

                ok = enviar_relatorio_semanal(dados_carteira)

                if ok:
                    registrar_envio_relatorio(list(ativos_rel.keys()))
                    st.success(f"✅ relatório enviado para {st.secrets['email']['destinatario']}! verifique sua caixa de entrada.")
                    st.rerun()
                else:
                    st.error("erro ao enviar. verifique as configurações de email em secrets.toml.")
        except Exception as e:
            st.error(f"erro ao montar relatório: {e}")

with st.expander("📋 histórico de envios", expanded=False):
    historico = listar_relatorios_enviados(limite=5)
    if historico:
        from datetime import datetime
        for h in historico:
            dt_h = datetime.fromisoformat(h['enviado_em'])
            tickers_h = h['tickers_incluidos'].split(',') if h['tickers_incluidos'] else []
            st.markdown(
                f'<div style="font-family:Courier New; font-size:0.8rem; color:#888; padding:6px 0; border-bottom:1px solid #1e1e1e;">'
                f'📧 {dt_h.strftime("%d/%m/%Y %H:%M")} — {len(tickers_h)} ativos incluídos</div>',
                unsafe_allow_html=True
            )
    else:
        st.caption("nenhum envio registrado.")