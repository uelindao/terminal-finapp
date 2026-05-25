import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import json as _json
from fredapi import Fred
from utils.ai_client import chamar_ia, SYSTEM_ANALISTA, SYSTEM_TESE
from utils.earnings_scraper import buscar_resultados
from bcb import sgs
import logging
import requests

# silenciar alertas vermelhos do yahoo finance no terminal
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# importações do ecossistema finapp
from utils.auth import require_auth, render_user_badge
from utils.style import aplicar_tema
from utils.tickers import get_opcoes_selectbox, ticker_from_label, mapear_ticker_base, FII_TODOS, BRASIL_TODOS, XSTOCKS_TODOS
from database.db import listar_watchlists, listar_watchlist, get_todos_fundamentos_cache, salvar_fundamento_cache, init_db, get_historico_score, get_health_scores
from utils.scrapers import buscar_dados_b3, buscar_dados_us

# componentes do design system
from utils.components import page_header, section_title, metric_card, status_card, empty_state, inject_keyboard_shortcuts
from utils.formatters import fmt_preco, fmt_pct, fmt_numero
from utils.charts import base_layout, CORES_SERIES, base100, linha

# 1. configuração da página
st.set_page_config(page_title="terminal finapp | research", layout="wide", page_icon="🔬")

# 2. barreira de segurança multi-usuário
if not require_auth():
    st.stop()

# 3. renderizações pós-login
render_user_badge()
aplicar_tema()
inject_keyboard_shortcuts()
init_db()

CACHE_FUNDAMENTOS = get_todos_fundamentos_cache()

# ==========================================
# MOTOR DE BUSCA GLOBAL (YAHOO FINANCE)
# ==========================================
def buscar_ativo_yahoo(query):
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}"
    headers = {'user-agent': 'Mozilla/5.0'}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        return r.json().get('quotes', [])
    except:
        return []

# ==========================================
# GESTÃO DE ESTADO E SIDEBAR
# ==========================================
if 'research_ticker' not in st.session_state:
    st.session_state['research_ticker'] = "PETR4.SA"

if 'research_ticker_externo' in st.session_state:
    st.session_state['research_ticker'] = st.session_state.pop('research_ticker_externo')

with st.sidebar:
    section_title("🔬 modo de análise")
    modo_pesquisa = st.radio("selecione o escopo:", ["Deep Dive (Individual)", "Comparativo (Múltiplos)"], label_visibility="collapsed")
    
    st.markdown("---")
    
    if modo_pesquisa == "Deep Dive (Individual)":
        section_title("pesquisar ativo")
        
        # --- NOVA BUSCA GLOBAL (YAHOO FINANCE API) ---
        termo = st.text_input("buscar qualquer ativo global:", placeholder="nome ou ticker (ex: nubank, aapl)...")
        if st.button("🔍 buscar ativo", use_container_width=True):
            if termo:
                with st.spinner("procurando na rede global..."):
                    resultados = buscar_ativo_yahoo(termo)
                    if resultados:
                        melhor_match = resultados[0].get('symbol')
                        if melhor_match:
                            st.session_state['research_ticker'] = melhor_match
                            st.rerun()
                    else:
                        st.warning("ativo não encontrado.")
        
        st.markdown("<div style='text-align: center; color: #555; padding: 10px 0;'>ou selecione da base:</div>", unsafe_allow_html=True)
        
        # --- LISTA PADRÃO COM PROTEÇÃO PARA ATIVOS EXTERNOS ---
        opcoes = get_opcoes_selectbox()
        ticker_atual = st.session_state['research_ticker']
        
        # Verifica se o ticker pesquisado está na lista padrão, se não, adiciona ele no topo
        ticker_presente = any(ticker_atual in opt for opt in opcoes)
        if not ticker_presente:
            opcoes.insert(0, f"{ticker_atual} — Ativo Externo")
        
        idx_default = 0
        for i, opt in enumerate(opcoes):
            if ticker_atual in opt:
                idx_default = i
                break

        escolha = st.selectbox("lista de ativos:", opcoes, index=idx_default, label_visibility="collapsed")
        
        # Extrair ticker com segurança
        if " — " in escolha:
            ticker_limpo = escolha.split(" — ")[0].strip()
        else:
            ticker_limpo = ticker_from_label(escolha)
            
        # Atualiza a página caso o usuário escolha outro item da lista dropdown
        if ticker_limpo and ticker_limpo != st.session_state['research_ticker']:
            st.session_state['research_ticker'] = ticker_limpo
            st.rerun()
            
    else:
        section_title("comparar ativos")
        ativos_comp = st.multiselect("selecione os ativos:", 
                                     options=BRASIL_TODOS + XSTOCKS_TODOS,
                                     default=["PETR4.SA", "VALE3.SA", "ITUB4.SA"])
    
    st.markdown("---")
    st.caption("v2.4 — busca universal implementada")

# Trava de segurança para números
def safe_float(val):
    try:
        if val is None or pd.isna(val): return None
        return float(val)
    except: return None

def calcular_crescimento_implicito(preco, eps, wacc, g_terminal, n_anos):
    try:
        if eps is None or eps <= 0 or preco is None or preco <= 0:
            return None
        if wacc <= g_terminal:
            return None
            
        def valor_dcf(g):
            soma_fc = sum((eps * (1 + g)**t) / ((1 + wacc)**t) for t in range(1, n_anos + 1))
            valor_term = (eps * (1 + g)**n_anos * (1 + g_terminal)) / (wacc - g_terminal)
            valor_term_descontado = valor_term / ((1 + wacc)**n_anos)
            return soma_fc + valor_term_descontado
            
        lo = -0.5
        hi = 3.0
        for _ in range(200):
            mid = (lo + hi) / 2
            try:
                if valor_dcf(mid) > preco:
                    hi = mid
                else:
                    lo = mid
            except:
                return None
        return mid
    except:
        return None

# ==========================================
# MODO 2: COMPARATIVO MULTI-ATIVOS
# ==========================================
if modo_pesquisa == "Comparativo (Múltiplos)":
    page_header("⚖️ comparativo de mercado", "análise relativa de múltiplos e performance em base 100.")
    
    if not ativos_comp:
        st.info("selecione ativos na barra lateral para iniciar a comparação.")
    else:
        with st.spinner("sincronizando matriz de múltiplos..."):
            dados_comp = []
            try:
                hist_all = yf.download(ativos_comp, period="10y", progress=False)['Close']
                if isinstance(hist_all, pd.Series): hist_all = hist_all.to_frame(name=ativos_comp[0])
                hist_all = hist_all.ffill().dropna(how='all')
                if hist_all.index.tz is not None: hist_all.index = hist_all.index.tz_localize(None)
            except: hist_all = pd.DataFrame()
            
            for t in ativos_comp:
                t_base = mapear_ticker_base(t)
                try:
                    info = yf.Ticker(t_base).info
                    cache_d = CACHE_FUNDAMENTOS.get(t_base, {})
                    dados_comp.append({
                        "ticker": t,
                        "p/l": safe_float(cache_d.get('p/l')) or safe_float(info.get('trailingPE')),
                        "p/vp": safe_float(cache_d.get('p/vp')) or safe_float(info.get('priceToBook')),
                        "roe%": safe_float(cache_d.get('roe%')) or (safe_float(info.get('returnOnEquity', 0))*100),
                        "dy%": safe_float(cache_d.get('dy%')) or (safe_float(info.get('dividendYield', 0))*100),
                        "mrg_liq%": safe_float(cache_d.get('margem%')) or (safe_float(info.get('profitMargins', 0))*100),
                        "mkt_cap": safe_float(info.get('marketCap')) or safe_float(cache_d.get('market_cap'))
                    })
                except: pass

            df_comp = pd.DataFrame(dados_comp)
            c1, c2 = st.columns([6, 4])
            with c1:
                st.markdown("**matriz de múltiplos quantitativos**")
                if not df_comp.empty:
                    st.dataframe(df_comp.style.format({"p/l": "{:.2f}", "p/vp": "{:.2f}", "roe%": "{:.1f}%", "dy%": "{:.1f}%", "mrg_liq%": "{:.1f}%", "mkt_cap": "${:,.0f}"}), use_container_width=True, hide_index=True)
            with c2:
                st.markdown("**performance relativa (base 100 — 10 anos)**")
                if not hist_all.empty:
                    df_b100 = (hist_all / hist_all.iloc[0]) * 100
                    fig_b100 = base100(df_b100, height=350)
                    st.plotly_chart(fig_b100, use_container_width=True)
    st.stop()

# ==========================================
# MODO 1: DEEP DIVE (INDIVIDUAL)
# ==========================================
ticker = st.session_state['research_ticker']
t_base = mapear_ticker_base(ticker)
is_fii = ticker in FII_TODOS or (ticker.endswith("11.SA") and ticker not in ['TAEE11.SA', 'KLBN11.SA', 'ENGI11.SA'])

@st.cache_resource(ttl=3600)
def carregar_dados_ativo(tk):
    acao = yf.Ticker(tk)

    # ── histórico: bloco isolado — falha aqui é fatal ──────────────────────
    hist = pd.DataFrame()
    try:
        hist = acao.history(period="10y", auto_adjust=True)
        # yfinance >=0.2.x pode retornar MultiIndex; achata para índice simples
        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = hist.columns.get_level_values(0)
        # remove timezone do índice para compatibilidade com plotly/pandas
        if not hist.empty and getattr(hist.index, "tz", None) is not None:
            hist.index = hist.index.tz_localize(None)
    except Exception:
        pass  # hist permanece vazio — tratado logo abaixo

    # ── info: bloco isolado — falha aqui NÃO mata o histórico ──────────────
    info = {}
    try:
        raw_info = acao.info
        if isinstance(raw_info, dict):
            info = raw_info
    except Exception:
        pass  # info fica {} — fallback para CACHE_FUNDAMENTOS

    if hist.empty:
        return None, pd.DataFrame(), {}

    return acao, hist, info

acao_obj, df_hist, info_dict = carregar_dados_ativo(t_base)
if acao_obj is None or df_hist.empty:
    empty_state("❌", "ativo não encontrado", "não foi possível carregar os dados históricos.")
    st.stop()

cache_d = CACHE_FUNDAMENTOS.get(t_base, {})

# ── Fallback: busca fundamentos diretamente quando não está no cache ──────
# Ativos externos (buscados manualmente) não passam pelo sync do screener.
_qualidade_cache = cache_d.get('qualidade_dados', 0) if cache_d else 0
if not cache_d or _qualidade_cache < 30:
    with st.spinner(f"buscando fundamentos de {t_base}..."):
        try:
            _fund_fresh = (
                buscar_dados_b3(t_base) if t_base.endswith('.SA')
                else buscar_dados_us(t_base)
            )
            if _fund_fresh and _fund_fresh.get('qualidade_dados', 0) > 0:
                cache_d = _fund_fresh
                # Persiste no cache para próximas visitas
                salvar_fundamento_cache(t_base, _fund_fresh)
        except Exception as _e_fund:
            logging.getLogger(__name__).warning(
                f"[research] falha ao buscar fundamentos {t_base}: {_e_fund}"
            )

# --- HEADER & MÉTRICAS ---
nome_exibicao = info_dict.get('longName') or info_dict.get('shortName') or cache_d.get('nome') or ticker
moeda = "r$" if ticker.endswith(".SA") else "$"
setor_raw = cache_d.get('setor') or info_dict.get('sector')
setor = "logística (fii)" if "logística" in str(setor_raw).lower() else (setor_raw if setor_raw else ("fundo imobiliário" if is_fii else "mercado global"))

page_header(f"🔬 {ticker.lower()}", f"{nome_exibicao.lower()} | {setor.lower()}")

c1, c2, c3, c4 = st.columns(4)
if is_fii:
    pvp = safe_float(cache_d.get('p/vp')) or safe_float(info_dict.get('priceToBook'))
    dy = safe_float(cache_d.get('dy%')) or (safe_float(info_dict.get('dividendYield', 0)) * 100)
    mcap = safe_float(info_dict.get('marketCap')) or safe_float(cache_d.get('market_cap', 0))
    assets = safe_float(info_dict.get('totalAssets'))
    with c1: metric_card("preço / vp", f"{pvp:.2f}" if pvp is not None else "n/d", "desconto" if pvp and pvp < 1 else ("ágio" if pvp else ""), "bull" if pvp and pvp < 1 else "bear")
    with c2: metric_card("dividend yield", fmt_pct(dy), "12m", "bull" if dy and dy > 8 else "muted")
    with c3: metric_card("mkt cap", fmt_numero(mcap, moeda))
    with c4: metric_card("patrimônio líq.", fmt_numero(assets, moeda))
else:
    pl = safe_float(cache_d.get('p/l')) or safe_float(info_dict.get('trailingPE')) or safe_float(info_dict.get('forwardPE'))
    roe = safe_float(cache_d.get('roe%')) or (safe_float(info_dict.get('returnOnEquity', 0)) * 100)
    mrg = safe_float(cache_d.get('margem%')) or (safe_float(info_dict.get('profitMargins', 0)) * 100)
    dy = safe_float(cache_d.get('dy%')) or (safe_float(info_dict.get('dividendYield', 0)) * 100)
    with c1: metric_card("preço / lucro", f"{pl:.1f}" if pl is not None else "n/d", "valuation")
    with c2: metric_card("r.o.e", fmt_pct(roe), "rentabilidade", "bull" if roe and roe > 15 else "muted")
    with c3: metric_card("margem líq.", fmt_pct(mrg), "eficiência", "bull" if mrg and mrg > 10 else "bear")
    with c4: metric_card("div yield", fmt_pct(dy), "12m")

st.markdown("<br>", unsafe_allow_html=True)

# --- EVOLUÇÃO DO HEALTH SCORE (últimos 180 dias) ---
historico = get_historico_score(t_base, dias=180)
if len(historico) >= 3:
    section_title("📈 evolução do health score")
    df_hist_score = pd.DataFrame(historico)
    df_hist_score['calculado_em'] = pd.to_datetime(df_hist_score['calculado_em'])
    df_hist_score = df_hist_score.set_index('calculado_em')
    fig_score = linha(df_hist_score, x_col=None, y_col='score',
                      titulo=f"health score — {ticker} (180 dias)",
                      cor="#FF9900", height=220)
    fig_score.add_hline(y=65, line_color="#00C853", line_dash="dash",
                        line_width=1, annotation_text="acumulação")
    fig_score.add_hline(y=40, line_color="#FF1744", line_dash="dash",
                        line_width=1, annotation_text="reduzir")
    fig_score.update_yaxes(range=[0, 100])
    st.plotly_chart(fig_score, use_container_width=True)

# ── HEALTH RESULT DO BANCO (para o prompt de IA) ─────────────────────────
_hs_all = get_health_scores()
_hs_map = {r['ticker']: r for r in (_hs_all or [])}
_hs_row = _hs_map.get(t_base, {})
if _hs_row:
    _raw = _hs_row.get('alertas_venda', '{}')
    _p   = _json.loads(_raw) if isinstance(_raw, str) else (_raw or {})
    health_result = {
        'score':     _hs_row.get('score', 50),
        'status':    (_p.get('alertas') or ['—'])[0],
        'alertas':   _p.get('alertas', []),
        'breakdown': _p.get('breakdown', {}),
    }
else:
    health_result = {'score': 50, 'status': '—', 'alertas': [], 'breakdown': {}}

# ── SEÇÃO: RESULTADOS FINANCEIROS TRIMESTRAIS ────────────────────────────
section_title("📊 resultados financeiros")

with st.spinner("buscando resultados..."):
    _earnings = buscar_resultados(t_base)

if _earnings.get('is_fii'):
    st.caption(
        "FIIs publicam relatórios mensais de proventos, não resultados trimestrais. "
        "consulte o histórico de dividendos na seção acima."
    )

elif _earnings.get('erro') and not _earnings.get('historico'):
    status_card(
        "resultados indisponíveis",
        f"não foi possível carregar os resultados para {t_base}. "
        "tente novamente em alguns minutos.",
        tipo="amber",
    )

else:
    # ── PRÓXIMA DATA ─────────────────────────────────────────────────────
    _prox_data = _earnings.get('proxima_data')
    if _prox_data:
        _hoje = datetime.date.today()
        try:
            _dt_prox  = datetime.datetime.strptime(_prox_data, '%d/%m/%Y').date()
            _dias_ate = (_dt_prox - _hoje).days
            if _dias_ate < 0:
                _cor_prox, _label_prox = "muted", f"último: {_prox_data}"
            elif _dias_ate == 0:
                _cor_prox, _label_prox = "bear", "HOJE"
            elif _dias_ate <= 7:
                _cor_prox, _label_prox = "bear", f"em {_dias_ate} dias ({_prox_data})"
            elif _dias_ate <= 30:
                _cor_prox, _label_prox = "amber", f"em {_dias_ate} dias ({_prox_data})"
            else:
                _cor_prox, _label_prox = "muted", _prox_data
        except Exception:
            _cor_prox, _label_prox = "muted", _prox_data

        _col_prox1, _col_prox2, _col_prox3 = st.columns(3)
        with _col_prox1:
            metric_card(
                "próximo resultado", _label_prox,
                f"fonte: {_earnings.get('fonte', '—')}",
                _cor_prox,
            )
        if _earnings.get('eps_estimado'):
            with _col_prox2:
                metric_card(
                    "eps estimado (próximo)",
                    f"$ {_earnings['eps_estimado']:.2f}",
                    "consenso de analistas",
                )
        if _earnings.get('receita_est'):
            with _col_prox3:
                metric_card(
                    "receita estimada",
                    f"$ {_earnings['receita_est']:.1f}B",
                    "consenso de analistas",
                )

    # ── HISTÓRICO DE RESULTADOS ──────────────────────────────────────────
    _earn_hist = _earnings.get('historico', [])
    _is_us     = not t_base.endswith('.SA')

    if _earn_hist:
        section_title(f"📈 histórico trimestral (últimos {len(_earn_hist)} trimestres)")

        _div_style = (
            '<div style="height:1px; background:#111; margin:4px 0;"></div>'
        )
        _lbl = (
            '<div style="font-family:Courier New; '
            'font-size:0.78rem; color:#888;">{label}<br>'
            '<span style="color:{cor};">{valor}</span></div>'
        )

        for _entry in _earn_hist:
            _c1, _c2, _c3, _c4, _c5 = st.columns(5)

            with _c1:
                st.markdown(
                    f'<div style="font-family:Courier New; color:#FF9900; '
                    f'font-size:0.82rem; font-weight:bold;">'
                    f'{_entry.get("periodo", "—")}</div>',
                    unsafe_allow_html=True,
                )

            with _c2:
                _rec = _entry.get('receita')
                if _rec is not None:
                    _un = "B" if _is_us else "M"
                    st.markdown(
                        _lbl.format(
                            label="receita",
                            cor="#E0E0E0",
                            valor=f"{_rec:.2f}{_un}",
                        ),
                        unsafe_allow_html=True,
                    )

            with _c3:
                _luc = _entry.get('lucro')
                if _luc is not None:
                    _un = "B" if _is_us else "M"
                    _cor_l = "#00C853" if _luc > 0 else "#FF1744"
                    st.markdown(
                        _lbl.format(
                            label="lucro líq.",
                            cor=_cor_l,
                            valor=f"{_luc:+.2f}{_un}",
                        ),
                        unsafe_allow_html=True,
                    )

            with _c4:
                if _is_us:
                    _eps_r = _entry.get('eps_real')
                    _eps_e = _entry.get('eps_est')
                    if _eps_r is not None:
                        _cor_e = "#00C853" if _eps_r >= (_eps_e or 0) else "#FF1744"
                        _est   = f" (est: ${_eps_e:.2f})" if _eps_e else ""
                        st.markdown(
                            _lbl.format(
                                label="eps",
                                cor=_cor_e,
                                valor=f"${_eps_r:.2f}{_est}",
                            ),
                            unsafe_allow_html=True,
                        )
                else:
                    _lpa = _entry.get('lpa')
                    if _lpa is not None:
                        st.markdown(
                            _lbl.format(
                                label="lpa",
                                cor="#E0E0E0",
                                valor=f"R${_lpa:.2f}",
                            ),
                            unsafe_allow_html=True,
                        )

            with _c5:
                if _is_us:
                    _surp = _entry.get('surpresa')
                    if _surp is not None:
                        _cor_s  = "#00C853" if _surp >= 0 else "#FF1744"
                        _icon_s = "▲" if _surp >= 0 else "▼"
                        st.markdown(
                            _lbl.format(
                                label="surpresa eps",
                                cor=_cor_s,
                                valor=f"{_icon_s} {abs(_surp):.1f}%",
                            ),
                            unsafe_allow_html=True,
                        )
                else:
                    _mrg = _entry.get('margem')
                    if _mrg is not None:
                        _cor_m = (
                            "#00C853" if _mrg > 10
                            else "#FF9900" if _mrg > 0
                            else "#FF1744"
                        )
                        st.markdown(
                            _lbl.format(
                                label="margem",
                                cor=_cor_m,
                                valor=f"{_mrg:.1f}%",
                            ),
                            unsafe_allow_html=True,
                        )

            st.markdown(_div_style, unsafe_allow_html=True)

        # ── Gráfico de evolução do lucro ─────────────────────────────────
        _lucros_validos = [
            (e['periodo'], e['lucro'])
            for e in _earn_hist
            if e.get('lucro') is not None
        ]
        if len(_lucros_validos) >= 3:
            _peri_g  = [x[0] for x in reversed(_lucros_validos)]
            _luc_g   = [x[1] for x in reversed(_lucros_validos)]
            _cores_g = ["#00C853" if l > 0 else "#FF1744" for l in _luc_g]

            _fig_earn = go.Figure(go.Bar(
                x=_peri_g, y=_luc_g,
                marker_color=_cores_g,
                hovertemplate="%{x}<br>lucro: %{y:.2f}<extra></extra>",
            ))
            _un_g = "B (USD)" if _is_us else "M (BRL)"
            _lay_earn = base_layout(
                height=220,
                title=f"lucro líquido trimestral ({_un_g})",
            )
            _fig_earn.update_layout(**_lay_earn)
            _fig_earn.add_hline(y=0, line_color="#333", line_width=1)
            st.plotly_chart(_fig_earn, use_container_width=True)

# ── SEÇÃO: ANÁLISE IA — DEEPSEEK V4 PRO ──────────────────────────────────
section_title("🧠 análise ia — deepseek v4 pro")


def montar_prompt_ativo(
    ticker, nome, setor, tipo_mercado,
    fundamentos, health_result,
    preco_atual, var_1d, macro_context
) -> str:
    """
    Monta prompt em ordem cache-friendly.
    Estático primeiro (identidade → fundamentos → score → macro), volátil por último.
    """
    fund = fundamentos or {}

    # ── BLOCO 1: IDENTIDADE — mais estático, cacheia melhor ──
    b1 = (
        f"ativo: {ticker.upper()}\n"
        f"nome: {nome}\n"
        f"setor: {setor}\n"
        f"mercado: {tipo_mercado}\n"
        f"tipo: {'fii' if '11.SA' in ticker else 'acao br' if '.SA' in ticker else 'acao us'}\n"
    )

    # ── BLOCO 2: FUNDAMENTOS — muda a cada atualização semanal ──
    b2 = (
        f"\nfundamentos:\n"
        f"p/l: {fund.get('p/l', 'n/d')}\n"
        f"p/vp: {fund.get('p/vp', 'n/d')}\n"
        f"roe: {fund.get('roe%', 'n/d')}%\n"
        f"dividend yield: {fund.get('dy%', 'n/d')}%\n"
        f"margem liquida: {fund.get('margem%', 'n/d')}%\n"
        f"ev/ebitda: {fund.get('ev/ebitda', 'n/d')}\n"
        f"qualidade dos dados: {fund.get('qualidade_dados', 0)}%\n"
    )

    # ── BLOCO 3: HEALTH SCORE — muda a cada recálculo ──
    alertas      = health_result.get('alertas', [])
    breakdown    = health_result.get('breakdown', {})
    alertas_txt  = "\n".join([f"- {a}" for a in alertas[:8]])
    bkdown_txt   = "\n".join([f"- {k}: {v}" for k, v in list(breakdown.items())[:10]])
    b3 = (
        f"\nhealth score: {health_result.get('score', 50)}/100\n"
        f"status: {health_result.get('status', 'n/d')}\n\n"
        f"alertas do motor quantitativo:\n{alertas_txt}\n\n"
        f"breakdown:\n{bkdown_txt}\n"
    )

    # ── BLOCO 4: CONTEXTO MACRO — muda mensalmente ──
    b4 = (
        f"\ncontexto macro:\n"
        f"selic: {macro_context.get('selic', 10.75):.2f}%\n"
        f"vix: {macro_context.get('vix', 15.0):.1f}\n"
        f"ipca: {macro_context.get('ipca', 4.5):.1f}%\n"
        f"ambiente: {macro_context.get('label', 'neutro')}\n"
    )

    # ── BLOCO 5: DADOS VOLÁTEIS — SEMPRE POR ÚLTIMO ──
    b5 = (
        f"\ncotacao atual: r$ {preco_atual:,.2f}\n"
        f"variacao hoje: {var_1d:+.2f}%\n"
    )

    instrucao = (
        "\ncom base nos dados acima, forneça a análise nos seguintes tópicos:\n\n"
        "tese central: argumento principal para manter ou não este ativo (2 linhas máximo)\n\n"
        "pontos positivos: (3 bullets)\n"
        "- o que está funcionando nos fundamentos ou no técnico\n\n"
        "riscos principais: (3 bullets)\n"
        "- o que pode destruir a tese ou prejudicar o retorno\n\n"
        "impacto macro: (2 bullets)\n"
        "- como o ambiente atual de juros e risco afeta especificamente este ativo\n\n"
        "métrica para monitorar:\n"
        "- uma métrica específica com frequência sugerida de acompanhamento\n\n"
        "seja objetivo. use os dados fornecidos. não invente números."
    )

    return b1 + b2 + b3 + b4 + b5 + instrucao


_col_ia1, _col_ia2, _col_ia3 = st.columns([2, 1, 1])
with _col_ia1:
    st.markdown(
        '<div style="font-family:Courier New; font-size:0.72rem; color:#333; line-height:1.5;">'
        'deepseek v4 pro — análise com base em fundamentos, health score e macro. '
        'não é recomendação.</div>',
        unsafe_allow_html=True,
    )
with _col_ia2:
    usar_thinking = st.checkbox(
        "modo reasoning",
        value=False,
        key="ia_thinking",
        help="ativa raciocínio profundo — mais lento e caro, use para decisões importantes",
    )
with _col_ia3:
    btn_analise_ia = st.button(
        "🧠 analisar",
        type="primary",
        use_container_width=True,
        key="btn_analise_ia",
    )

if btn_analise_ia:
    macro_ctx = st.session_state.get("macro_context", {
        "selic": 10.75, "vix": 15.0, "ipca": 4.5, "label": "neutro"
    })

    preco_ia = float(df_hist['Close'].iloc[-1]) if not df_hist.empty else 0.0
    var_ia   = 0.0
    if len(df_hist) >= 2:
        _p_hoje = float(df_hist['Close'].iloc[-1])
        _p_ant  = float(df_hist['Close'].iloc[-2])
        if _p_ant > 0:
            var_ia = (_p_hoje - _p_ant) / _p_ant * 100

    _prompt_ia = montar_prompt_ativo(
        ticker        = t_base,
        nome          = cache_d.get("nome", nome_exibicao),
        setor         = setor,
        tipo_mercado  = ("brasil (b3)" if t_base.endswith(".SA") else "eua"),
        fundamentos   = cache_d,
        health_result = health_result,
        preco_atual   = preco_ia,
        var_1d        = var_ia,
        macro_context = macro_ctx,
    )

    chamar_ia(
        prompt_usuario = _prompt_ia,
        system         = SYSTEM_ANALISTA,
        max_tokens     = 900,
        temperatura    = 0.3,
        stream         = True,
        thinking       = usar_thinking,
    )
    st.session_state[f"ia_analise_{t_base}"] = True

elif st.session_state.get(f"ia_analise_{t_base}"):
    st.caption("análise já gerada nesta sessão. clique novamente para atualizar.")

# ── SEÇÃO: EXPORTAR TESE EM PDF ───────────────────────────────────────────
section_title("📄 exportar tese em pdf")

_col_pdf1, _col_pdf2 = st.columns([3, 1])
with _col_pdf1:
    st.markdown(
        '<div style="font-family:Courier New; font-size:0.72rem; color:#333;">'
        'gera um relatório profissional com fundamentos, análise ia e '
        'health score em formato pdf. o deepseek redige a tese completa '
        'antes da renderização — pode levar alguns segundos.</div>',
        unsafe_allow_html=True,
    )
with _col_pdf2:
    btn_gerar_pdf = st.button(
        "📄 gerar pdf",
        type             = "secondary",
        use_container_width = True,
        key              = "btn_gerar_pdf",
    )

if btn_gerar_pdf:
    # Variáveis derivadas do contexto já carregado na página
    _fund_pdf  = cache_d                  # fundamentos do cache
    _alertas   = health_result.get("alertas", [])
    _breakdown = health_result.get("breakdown", {})
    _macro_ctx = st.session_state.get("macro_context", {
        "selic": 10.75, "vix": 15.0, "ipca": 4.5, "label": "neutro"
    })
    _preco_pdf = float(df_hist['Close'].iloc[-1]) if not df_hist.empty else 0.0

    # 1. Gera texto da tese via DeepSeek (sem streaming — precisa do texto completo)
    with st.spinner("deepseek v4 pro redigindo tese..."):
        _prompt_pdf = (
            f"ativo: {t_base.upper()}\n"
            f"nome: {_fund_pdf.get('nome', nome_exibicao)}\n"
            f"setor: {setor}\n"
            f"tipo: {'fii' if '11.SA' in t_base else 'acao br' if '.SA' in t_base else 'acao us'}\n\n"
            f"fundamentos:\n"
            f"p/l: {_fund_pdf.get('p/l', 'n/d')}\n"
            f"p/vp: {_fund_pdf.get('p/vp', 'n/d')}\n"
            f"roe: {_fund_pdf.get('roe%', 'n/d')}%\n"
            f"dy: {_fund_pdf.get('dy%', 'n/d')}%\n"
            f"margem: {_fund_pdf.get('margem%', 'n/d')}%\n\n"
            f"health score: {health_result.get('score', 50)}/100\n"
            f"status: {health_result.get('status', 'n/d')}\n\n"
            f"alertas:\n"
            + "\n".join([f"- {a}" for a in _alertas[:6]])
            + f"\n\ncontexto macro:\n"
            f"selic: {_macro_ctx.get('selic', 10.75):.2f}%\n"
            f"vix: {_macro_ctx.get('vix', 15.0):.1f}\n"
            f"ambiente: {_macro_ctx.get('label', 'neutro')}\n\n"
            f"cotacao atual: r$ {_preco_pdf:,.2f}\n\n"
            "redija uma tese de investimento completa com: "
            "1. contexto do negocio, "
            "2. drivers de valor, "
            "3. riscos principais, "
            "4. valuation e veredicto. "
            "texto direto, sem asteriscos, letra minuscula."
        )
        _analise_pdf = chamar_ia(
            prompt_usuario = _prompt_pdf,
            system         = SYSTEM_TESE,
            max_tokens     = 1200,
            temperatura    = 0.3,
            stream         = False,
            thinking       = False,
        )

    # 2. Monta e disponibiliza o PDF
    with st.spinner("montando pdf..."):
        try:
            from utils.pdf_generator import gerar_tese_pdf
            _pdf_bytes = gerar_tese_pdf(
                ticker        = t_base,
                nome          = _fund_pdf.get("nome", nome_exibicao),
                setor         = setor,
                health_score  = health_result.get("score", 50),
                preco_atual   = _preco_pdf,
                fundamentos   = _fund_pdf,
                analise_ia    = _analise_pdf or "análise indisponível.",
                alertas       = _alertas,
                breakdown     = _breakdown,
                macro_context = _macro_ctx,
            )
            _nome_arquivo = (
                f"tese_{t_base.replace('.SA', '').lower()}_"
                f"{datetime.datetime.now().strftime('%Y%m%d')}.pdf"
            )
            st.download_button(
                label               = "⬇️ baixar tese em pdf",
                data                = _pdf_bytes,
                file_name           = _nome_arquivo,
                mime                = "application/pdf",
                type                = "primary",
                use_container_width = True,
                key                 = "btn_download_pdf",
            )
            st.success(f"✅ tese gerada: {_nome_arquivo}")
        except Exception as _e_pdf:
            st.error(f"erro ao gerar pdf: {_e_pdf}")

st.markdown("---")

# --- TABS ---
tab_tec, tab_earn, tab_fund, tab_dcf, tab_sent, tab_macro = st.tabs([
    "📈 análise técnica (10y)", "📊 demonstrações (dre)", "💎 fundamentos", "🧮 valuation lab (dcf reverso)", "📰 notícias & ia", "🌍 overlay macro (10y)"
])

with tab_tec:
    try:
        fig_tec = go.Figure()
        fig_tec.add_trace(go.Candlestick(x=df_hist.index, open=df_hist['Open'], high=df_hist['High'], low=df_hist['Low'], close=df_hist['Close'], name="price"))
        if len(df_hist) >= 50: fig_tec.add_trace(go.Scatter(x=df_hist.index, y=df_hist['Close'].rolling(50).mean(), name="mm50", line=dict(color=CORES_SERIES[1], width=1)))
        if len(df_hist) >= 200: fig_tec.add_trace(go.Scatter(x=df_hist.index, y=df_hist['Close'].rolling(200).mean(), name="mm200", line=dict(color=CORES_SERIES[3], width=1.5)))
        fig_tec.update_layout(**base_layout(height=500, title=f"price action histórico (10 anos): {ticker.lower()}"))
        fig_tec.update_layout(xaxis_rangeslider_visible=False)
        st.plotly_chart(fig_tec, use_container_width=True)
    except Exception as e: st.error(f"Erro gráfico técnico: {e}")

with tab_earn:
    if is_fii: st.info("💡 FIIs não possuem DRE trimestral padrão. Avalie os Rendimentos em Fundamentos.")
    else:
        st.subheader("receita vs lucro (últimos períodos)")
        try:
            fin = acao_obj.quarterly_financials
            if fin is None or (isinstance(fin, pd.DataFrame) and fin.empty): fin = acao_obj.financials
            if fin is not None and not fin.empty:
                l_rev = ['Total Revenue', 'Total Operating Revenue', 'Operating Revenue']
                l_net = ['Net Income', 'Net Income Common Stockholders', 'Net Income From Continuing Operations']
                row_rev = fin.index[fin.index.isin(l_rev)].tolist()
                row_net = fin.index[fin.index.isin(l_net)].tolist()
                if row_rev and row_net:
                    df_earn = pd.DataFrame({'Receita': fin.loc[row_rev[0]], 'Lucro Líquido': fin.loc[row_net[0]]}).sort_index()
                    df_earn.index = df_earn.index.astype(str)
                    fig_earn = go.Figure()
                    fig_earn.add_trace(go.Bar(x=df_earn.index, y=df_earn['Receita'], name="receita", marker_color=CORES_SERIES[1]))
                    fig_earn.add_trace(go.Bar(x=df_earn.index, y=df_earn['Lucro Líquido'], name="lucro", marker_color=CORES_SERIES[2]))
                    fig_earn.update_layout(**base_layout(height=400), barmode='group')
                    st.plotly_chart(fig_earn, use_container_width=True)
        except: st.error("Erro earnings.")

with tab_fund:
    c_f1, c_f2 = st.columns(2)
    with c_f1:
        st.markdown("**múltiplos e risco**")
        vol = fmt_pct(df_hist['Close'].pct_change().std() * np.sqrt(252) * 100) if len(df_hist) > 10 else "N/D"
        if is_fii:
            debt = safe_float(info_dict.get('totalDebt', 0))
            assets_t = safe_float(info_dict.get('totalAssets', 1))
            ltv = (debt / assets_t * 100) if assets_t > 0 else 0
            f_d = {"métrica": ["P/VP", "Yield (12m)", "Volatilidade Anual", "Alavancagem (Dívida/Ativos)", "Setor/Segmento"], 
                   "valor": [f"{pvp:.2f}" if pvp is not None else "N/D", fmt_pct(dy), vol, f"{ltv:.1f}%" if ltv > 0 else "baixa/nula", setor]}
        else:
            ev_e = safe_float(cache_d.get('ev/ebitda')) or safe_float(info_dict.get('enterpriseToEbitda'))
            pvp_val = safe_float(cache_d.get('p/vp')) or safe_float(info_dict.get('priceToBook'))
            beta_val = safe_float(info_dict.get('beta'))
            debt_val = safe_float(info_dict.get('debtToEquity'))
            
            f_d = {
                "métrica": ["EV/EBITDA", "P/VP", "Volatilidade Anual", "Beta", "Dívida/Patrimônio"], 
                "valor": [
                    f"{ev_e:.2f}" if ev_e is not None else "N/D", 
                    f"{pvp_val:.2f}" if pvp_val is not None else "N/D", 
                    vol, 
                    f"{beta_val:,.2f}" if beta_val is not None else "N/D", 
                    f"{debt_val:,.1f}%" if debt_val is not None else "N/D"
                ]
            }
        st.table(pd.DataFrame(f_d))
    with c_f2:
        st.markdown("**descrição**")
        st.write(info_dict.get('longBusinessSummary', 'Sem descrição.')[:800] + "...")

with tab_dcf:
    if is_fii:
        empty_state("🧮", "dcf não aplicável", "o modelo de dcf reverso é projetado para ações com lucro por ação. fiis são avaliados por p/vp e dividend yield.")
    else:
        eps_base = safe_float(info_dict.get('trailingEps')) or safe_float(info_dict.get('forwardEps'))
        preco_base = safe_float(df_hist['Close'].iloc[-1]) if not df_hist.empty else None
        is_us = not ticker.endswith('.SA')
        
        section_title("⚙️ parâmetros do modelo")
        
        c_dcf1, c_dcf2, c_dcf3, c_dcf4 = st.columns(4)
        with c_dcf1:
            eps_input = st.number_input("eps (lucro/ação)", value=float(eps_base) if eps_base and eps_base > 0 else 5.0, min_value=-100.0, step=0.01, format="%.2f")
        with c_dcf2:
            preco_input = st.number_input("preço atual", value=float(preco_base) if preco_base else 100.0, min_value=0.01, step=0.01, format="%.2f")
        with c_dcf3:
            wacc_pct = st.slider("wacc (custo capital %)", min_value=4.0, max_value=20.0, value=9.0 if is_us else 12.0, step=0.5, format="%.1f%%")
        with c_dcf4:
            g_term_pct = st.slider("crescimento terminal %", min_value=1.0, max_value=5.0, value=3.0, step=0.5, format="%.1f%%")
            
        c_dcf5, c_dcf6 = st.columns(2)
        with c_dcf5:
            n_anos = st.slider("horizonte de projeção (anos)", min_value=5, max_value=15, value=10, step=1)
        with c_dcf6:
            margem_seg_pct = st.slider("margem de segurança (%)", min_value=0, max_value=40, value=15, step=5)
            
        wacc = wacc_pct / 100
        g_terminal = g_term_pct / 100
        
        st.markdown("---")
        
        g_implicito = calcular_crescimento_implicito(preco_input, eps_input, wacc, g_terminal, n_anos)
        
        section_title("📊 crescimento implícito no preço atual")
        
        if g_implicito is None:
            st.warning("não foi possível calcular. verifique se o eps é positivo e o wacc é maior que o crescimento terminal.")
        else:
            g_implicito_pct = g_implicito * 100
            preco_com_ms = preco_input * (1 - (margem_seg_pct / 100))
            
            c_res1, c_res2, c_res3, c_res4 = st.columns(4)
            with c_res1:
                metric_card("crescimento implícito (a.a.)", fmt_pct(g_implicito_pct), cor_delta="bull" if g_implicito_pct < 15 else "bear")
            with c_res2:
                metric_card("p/l implícito", f"{preco_input/eps_input:.1f}x" if eps_input > 0 else "n/d")
            with c_res3:
                metric_card("preço com margem segurança", f"{moeda.upper()} {preco_com_ms:.2f}")
            with c_res4:
                metric_card("horizonte analisado", f"{n_anos} anos")
                
            if g_implicito_pct < 8:
                interpretacao = "crescimento baixo precificado — assimetria favorável se a empresa crescer acima disso."
                cor_int = "bull"
            elif g_implicito_pct <= 20:
                interpretacao = "crescimento moderado a alto precificado — valuation justo se tese de crescimento se confirmar."
                cor_int = "amber"
            else:
                interpretacao = "crescimento muito alto precificado — risco elevado de decepção. exige execução perfeita."
                cor_int = "bear"
                
            status_card("interpretação do valuation", interpretacao, cor_int)
            
            section_title("🗺️ mapa de sensibilidade — preço justo estimado por cenário")
            
            cenarios_g = [-5, 0, 5, 8, 10, 12, 15, 20, 25]
            cenarios_wacc = [round(wacc_pct - 2, 1), wacc_pct, round(wacc_pct + 2, 1)]
            
            dados_sens = []
            for wacc_c in cenarios_wacc:
                linha = {}
                w_c_dec = wacc_c / 100
                for g_c in cenarios_g:
                    g_c_dec = g_c / 100
                    try:
                        if w_c_dec <= g_terminal:
                            linha[f"g={g_c}%"] = "—"
                        else:
                            vp_soma = sum(eps_input * (1 + g_c_dec)**t / (1 + w_c_dec)**t for t in range(1, n_anos + 1))
                            vp_term = (eps_input * (1 + g_c_dec)**n_anos * (1 + g_terminal)) / (w_c_dec - g_terminal) / ((1 + w_c_dec)**n_anos)
                            linha[f"g={g_c}%"] = round(vp_soma + vp_term, 2)
                    except:
                        linha[f"g={g_c}%"] = "—"
                dados_sens.append(linha)
                
            df_sens = pd.DataFrame(dados_sens, index=[f"wacc {w}%" for w in cenarios_wacc])
            
            st.dataframe(df_sens, use_container_width=True, hide_index=False)
            st.caption(f"valores em {moeda.upper()} | célula verde = subvalorizado vs preço atual de {preco_input} | linha destacada = wacc configurado acima.")
            
            fig = go.Figure()
            for i, wacc_c in enumerate(cenarios_wacc):
                y_vals = []
                for g_c in cenarios_g:
                    val = df_sens.loc[f"wacc {wacc_c}%", f"g={g_c}%"]
                    y_vals.append(val if val != "—" else None)
                    
                fig.add_trace(go.Scatter(x=cenarios_g, y=y_vals, name=f"wacc {wacc_c}%", line=dict(color=CORES_SERIES[i % len(CORES_SERIES)])))
                
            fig.add_hline(y=preco_input, line_color="#FF9900", line_dash="dash", annotation_text="preço atual")
            fig.update_layout(**base_layout(height=380, title="preço justo estimado por taxa de crescimento e wacc"))
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("---")
            if st.button("🧠 ia: interpretar o valuation e gerar tese", type="primary"):
                _prompt_dcf = (
                    f"ativo: {ticker} | setor: {setor}\n\n"
                    f"modelo dcf reverso:\n"
                    f"eps: {eps_input:.2f} | wacc: {wacc_pct}% | g terminal: {g_term_pct}% | horizonte: {n_anos} anos\n\n"
                    f"resultado:\n"
                    f"crescimento implícito no preço: {g_implicito_pct:.1f}%\n"
                    f"preço atual: {moeda.upper()} {preco_input:.2f}\n\n"
                    "responda em 4 tópicos curtos, letra minúscula:\n"
                    "1. o crescimento implícito é realista para o setor?\n"
                    "2. comparação com pares do setor se souber.\n"
                    "3. cenário bull e bear para o preço em 3 anos.\n"
                    "4. recomendação (comprar / aguardar / evitar) com justificativa."
                )
                with st.spinner("deepseek analisando o valuation..."):
                    chamar_ia(
                        prompt_usuario = _prompt_dcf,
                        system         = SYSTEM_TESE,
                        max_tokens     = 600,
                        temperatura    = 0.3,
                        stream         = True,
                    )

with tab_sent:
    st.subheader("sentimento via notícias")
    try:
        news = acao_obj.news
        if news:
            for item in news[:5]:
                with st.container():
                    cn1, cn2 = st.columns([4, 1])
                    cn1.markdown(f"**{item.get('title')}**")
                    cn1.caption(f"{item.get('publisher')} | {datetime.datetime.fromtimestamp(item.get('providerPublishTime'))}")
                    if cn2.button("ia: analisar", key=item.get('uuid')):
                        with st.spinner("ia..."):
                            _res_news = chamar_ia(
                                prompt_usuario=(
                                    f"ativo: {ticker}\n\n"
                                    f"manchete: {item.get('title')}\n\n"
                                    "em 1 frase curta com letra minúscula, diga se esta notícia é "
                                    "positiva, negativa ou neutra para o ativo e por quê."
                                ),
                                system      = SYSTEM_ANALISTA,
                                max_tokens  = 120,
                                temperatura = 0.2,
                                stream      = False,
                            )
                            if _res_news:
                                st.info(_res_news)
                    st.markdown("---")
    except: st.info("Sem notícias.")

with tab_macro:
    st.subheader("estudo de correlação estrutural (10 anos)")
    ind_macro = st.selectbox("comparar com:", ["Taxa Selic (Brasil)", "IPCA (Inflação BR)", "Dólar Comercial (BRL=X)", "VIX (Volatilidade Global)"])
    inicio_macro = (datetime.datetime.now() - datetime.timedelta(days=365*10)).strftime('%Y-%m-%d')
    try:
        m_data = None
        if "Selic" in ind_macro: m_data, m_name = sgs.get({'selic': 432}, start=inicio_macro)['selic'], "selic %"
        elif "IPCA" in ind_macro: m_data, m_name = sgs.get({'ipca': 433}, start=inicio_macro)['ipca'], "ipca %"
        elif "Dólar" in ind_macro:
            m_data = yf.download("BRL=X", start=inicio_macro, progress=False)['Close']
            if isinstance(m_data, pd.DataFrame): m_data = m_data.iloc[:, 0]
            m_name = "usd/brl"
        elif "VIX" in ind_macro and "FRED_API_KEY" in st.secrets:
            m_data, m_name = Fred(api_key=st.secrets["FRED_API_KEY"]).get_series('VIXCLS', observation_start=inicio_macro), "vix index"
            
        if m_data is not None and not m_data.empty:
            m_data.index = pd.to_datetime(m_data.index).tz_localize(None)
            stk_p = df_hist['Close'].copy()
            stk_p.index = pd.to_datetime(stk_p.index).tz_localize(None)
            fig_macro = make_subplots(specs=[[{"secondary_y": True}]])
            fig_macro.add_trace(go.Scatter(x=stk_p.index, y=stk_p, name=ticker.lower(), line=dict(color="#FF9900")), secondary_y=False)
            fig_macro.add_trace(go.Scatter(x=m_data.index, y=m_data, name=m_name, line=dict(color="#00B0FF", dash="dot")), secondary_y=True)
            fig_macro.update_layout(**base_layout(height=450, title=f"{ticker.lower()} vs {ind_macro.lower()}"))
            st.plotly_chart(fig_macro, use_container_width=True)
    except: st.warning("Erro overlay.")

# --- TESE DE INVESTIMENTO (FOOTER) ---
st.markdown("---")
section_title("📋 tese de investimento — deepseek v4 pro")
if st.button("📝 gerar tese de longo prazo", use_container_width=True, type="secondary", key="btn_tese_footer"):
    val_pl  = safe_float(cache_d.get('p/l'))  or safe_float(info_dict.get('trailingPE'))
    val_pvp = safe_float(cache_d.get('p/vp')) or safe_float(info_dict.get('priceToBook'))
    val_roe = safe_float(cache_d.get('roe%')) or (safe_float(info_dict.get('returnOnEquity', 0)) * 100)
    val_dy  = safe_float(cache_d.get('dy%'))  or (safe_float(info_dict.get('dividendYield', 0)) * 100)
    debt_f  = safe_float(info_dict.get('totalDebt', 0))
    assets_f = safe_float(info_dict.get('totalAssets', 1))
    ltv_f   = (debt_f / assets_f * 100) if assets_f and assets_f > 0 else 0

    _prompt_tese = (
        f"ativo: {ticker.upper()}\n"
        f"setor: {setor}\n"
        f"tipo: {'fii' if is_fii else 'acao br' if ticker.endswith('.SA') else 'acao us'}\n\n"
        f"fundamentos:\n"
        f"p/l: {f'{val_pl:.2f}' if val_pl else 'n/d'}\n"
        f"p/vp: {f'{val_pvp:.2f}' if val_pvp else 'n/d'}\n"
        f"roe: {f'{val_roe:.1f}%' if val_roe else 'n/d'}\n"
        f"dividend yield: {f'{val_dy:.1f}%' if val_dy else 'n/d'}\n"
        f"alavancagem (dívida/ativos): {ltv_f:.1f}%\n"
        f"health score: {health_result.get('score', 50)}/100\n\n"
        "escreva uma tese de investimento de longo prazo em 4 parágrafos curtos. "
        "avalie se a alavancagem é adequada para o setor. "
        "conclua com uma visão de risco/retorno. letra minúscula."
    )
    with st.spinner("deepseek elaborando tese..."):
        chamar_ia(
            prompt_usuario = _prompt_tese,
            system         = SYSTEM_TESE,
            max_tokens     = 700,
            temperatura    = 0.3,
            stream         = True,
        )