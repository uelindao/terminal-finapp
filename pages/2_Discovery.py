import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import json
import plotly.graph_objects as go
import datetime
import time
from fredapi import Fred
from bcb import sgs
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── silenciar alertas vermelhos do yahoo finance no terminal ──
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# importações do ecossistema finapp
from utils.auth import require_auth, render_user_badge
from utils.style import aplicar_tema
from database.db import (
    listar_watchlist, get_health_scores, adicionar_ativo,
    listar_watchlists, criar_watchlist, get_watchlist_padrao,
    get_todos_fundamentos_cache, salvar_fundamento_cache, init_db
)
from utils.tickers import (
    SCREENER_B3, SCREENER_US, XSTOCKS_INDICES, FII_TODOS,
    BRASIL_TODOS, XSTOCKS_TODOS, BR_INDICES, mapear_ticker_base
)
from utils.health_engine import calcular_health_score
from utils.components import page_header, section_title, status_card, empty_state, inject_keyboard_shortcuts, metric_card
from utils.ai_client import chamar_ia, SYSTEM_ANALISTA
from utils.charts import base_layout

# 1. barreira de segurança multi-usuário
if not require_auth():
    st.stop()

# 3. renderizações pós-login
render_user_badge()
aplicar_tema()
inject_keyboard_shortcuts()

init_db()
CACHE_FUNDAMENTOS = get_todos_fundamentos_cache()

c_head1, c_head2, c_head3 = st.columns([6, 2, 2])
with c_head1:
    page_header("🎯 discovery — descoberta", "encontre assimetrias de mercado através de filtros quantitativos e inteligência artificial.")
with c_head2:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 sync cache b3 / fii", use_container_width=True, type="primary", help="sincroniza ações e fiis brasileiros."):
        st.session_state['run_sync_b3'] = True
with c_head3:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 sync cache eua", use_container_width=True, type="primary", help="sincroniza ativos do mercado americano."):
        st.session_state['run_sync_us'] = True

st.markdown("---")

def traduzir_setor(setor_raw: str) -> str:
    mapa_setores = {
        'Energy': '⛽ energia', 'Financial Services': '🏦 financeiro',
        'Technology': '💻 tecnologia', 'Healthcare': '🏥 saúde',
        'Consumer Cyclical': '🛒 consumo cíclico', 'Consumer Defensive': '🛒 consumo def.',
        'Industrials': '🏭 indústria', 'Basic Materials': '⛏️ materiais',
        'Real Estate': '🏢 imobiliário', 'Utilities': '⚡ utilities',
        'Communication Services': '📡 telecom', 'Financeiro': '🏦 financeiro',
    }
    return mapa_setores.get(setor_raw, setor_raw.lower() if setor_raw else '—')

# ==========================================
# ROTINAS DE SINCRONIZAÇÃO ASSÍNCRONA
# ==========================================
if st.session_state.get('run_sync_b3'):
    st.info("A iniciar sincronização massiva B3 (Ações + FIIs) em background...")
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    from utils.scrapers import buscar_dados_b3
    
    def fetch_and_save_b3(t):
        try:
            dados = buscar_dados_b3(t)
            salvar_fundamento_cache(t, dados)
            return True
        except: return False

    lista_completa = SCREENER_B3 + FII_TODOS
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_and_save_b3, t): t for t in lista_completa}
        total = len(lista_completa)
        concluidos = 0
        for future in as_completed(futures):
            concluidos += 1
            progress_bar.progress(concluidos / total)
            status_text.text(f"Sincronizando: {futures[future]} ({concluidos}/{total})...")
            
    st.session_state['run_sync_b3'] = False
    st.success("✅ Cache Nacional atualizada! Recarregando...")
    time.sleep(1.5)
    st.rerun()

if st.session_state.get('run_sync_us'):
    st.info("A iniciar extração massiva EUA em background...")
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    def fetch_and_save_us(t_base):
        try:
            info = yf.Ticker(t_base).info
            dados = {
                'nome': info.get('shortName', t_base),
                'setor': traduzir_setor(info.get('sector', '—')),
                'p/l': info.get('trailingPE', info.get('forwardPE', None)),
                'p/vp': info.get('priceToBook', None),
                'roe%': (info.get('returnOnEquity') * 100) if info.get('returnOnEquity') is not None else None,
                'dy%': (info.get('dividendYield') * 100) if info.get('dividendYield') is not None else 0,
                'market_cap': info.get('marketCap', 0),
                'ev/ebitda': info.get('enterpriseToEbitda', None),
                'margem%': (info.get('profitMargins') * 100) if info.get('profitMargins') is not None else None,
                'beta': info.get('beta', None)
            }
            salvar_fundamento_cache(t_base, dados)
            return True
        except: return False

    us_tickers_unicos = list(set([mapear_ticker_base(t) for t in SCREENER_US + XSTOCKS_INDICES]))
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_and_save_us, t): t for t in us_tickers_unicos}
        total = len(us_tickers_unicos)
        concluidos = 0
        for future in as_completed(futures):
            concluidos += 1
            progress_bar.progress(concluidos / total)
            status_text.text(f"Sincronizando EUA: {futures[future]} ({concluidos}/{total})...")
            
    st.session_state['run_sync_us'] = False
    st.success("✅ Cache EUA atualizada! Recarregando...")
    time.sleep(1.5)
    st.rerun()

@st.dialog("➕ salvar na watchlist")
def modal_salvar_screener(ticker: str, nome: str, mercado: str):
    st.markdown(f"**ativo:** {ticker.lower()} - {nome.lower()}")
    acao_wl = st.radio("destino:", ["watchlist existente", "criar nova watchlist"], horizontal=True, key=f"radio_dest_{ticker}")
    watchlists_disp = listar_watchlists()
    dest_id = None
    
    if acao_wl == "watchlist existente":
        opcoes_dest = {f"{wl['icone']} {wl['nome']}": wl['id'] for wl in watchlists_disp}
        sel_dest = st.selectbox("selecione a watchlist:", list(opcoes_dest.keys()), key=f"sel_exist_{ticker}")
        dest_id = opcoes_dest[sel_dest]
    else:
        nome_nova_wl = st.text_input("nome da nova watchlist:", placeholder="ex: radar de dividendos", key=f"input_nova_{ticker}")
    
    if st.button("💾 confirmar", type="primary", use_container_width=True, key=f"btn_conf_{ticker}"):
        if acao_wl == "criar nova watchlist":
            if nome_nova_wl.strip(): dest_id = criar_watchlist(nome_nova_wl.strip(), icone="🎯", cor="#00C853")
            else: return st.warning("digite um nome para a nova watchlist.")
        
        adicionar_ativo(ticker, nome, mercado, watchlist_id=dest_id)
        st.success(f"✅ {ticker.lower()} salvo com sucesso!")
        time.sleep(1); st.rerun()

@st.cache_data(ttl=3600, show_spinner=False)
def calcular_momentum(tickers_tuple: tuple) -> list[dict]:
    """Calcula força relativa de 52 semanas para uma lista de tickers."""
    tickers = list(tickers_tuple)
    resultados = []

    def processar(t):
        try:
            t_base = mapear_ticker_base(t)
            acao = yf.Ticker(t_base)
            hist = acao.history(period="1y", auto_adjust=True)
            if hist.empty or len(hist) < 50:
                return None

            close = hist['Close']
            preco_atual = close.iloc[-1]
            preco_1y = close.iloc[0]
            preco_6m = close.iloc[len(close)//2]
            preco_3m = close.iloc[int(len(close)*0.75)]
            preco_1m = close.iloc[-21] if len(close) >= 21 else close.iloc[0]

            ret_1y = (preco_atual / preco_1y - 1) * 100
            ret_6m = (preco_atual / preco_6m - 1) * 100
            ret_3m = (preco_atual / preco_3m - 1) * 100
            ret_1m = (preco_atual / preco_1m - 1) * 100

            mm50  = close.rolling(50).mean().iloc[-1]
            mm200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else close.mean()

            acima_mm50  = preco_atual > mm50
            acima_mm200 = preco_atual > mm200

            high_52w = close.max()
            low_52w  = close.min()
            dist_high = (preco_atual / high_52w - 1) * 100

            score_mom = 0
            if ret_1y > 0:  score_mom += 25
            if ret_6m > 0:  score_mom += 25
            if ret_3m > 0:  score_mom += 20
            if ret_1m > 0:  score_mom += 10
            if acima_mm50:  score_mom += 10
            if acima_mm200: score_mom += 10

            f_dados = CACHE_FUNDAMENTOS.get(t_base, {})

            return {
                'ticker': t,
                'nome': f_dados.get('nome', t_base),
                'setor': traduzir_setor(f_dados.get('setor', '—')),
                'preço atual': round(preco_atual, 2),
                'ret 1m (%)': round(ret_1m, 2),
                'ret 3m (%)': round(ret_3m, 2),
                'ret 6m (%)': round(ret_6m, 2),
                'ret 1y (%)': round(ret_1y, 2),
                'dist. topo 52w (%)': round(dist_high, 2),
                'acima mm50': '✅' if acima_mm50 else '❌',
                'acima mm200': '✅' if acima_mm200 else '❌',
                'score momentum': score_mom,
            }
        except:
            return None

    with ThreadPoolExecutor(max_workers=8) as ex:
        futuros = {ex.submit(processar, t): t for t in tickers}
        for fut in as_completed(futuros):
            res = fut.result()
            if res:
                resultados.append(res)

    return sorted(resultados, key=lambda x: x['score momentum'], reverse=True)


@st.cache_data(ttl=1800, show_spinner=False)
def calcular_heatmap_setorial(universo: str = "BR") -> list[dict]:
    """
    Agrupa health scores por setor e calcula métricas setoriais.
    Usa apenas dados já existentes no cache de fundamentos e health scores.
    Retorna lista de dicts ordenada por score médio descendente.
    """
    # Pega todos os health scores do banco
    todos_hs = get_health_scores()
    if not todos_hs:
        return []

    # Mapa ticker → score
    hs_map = {h['ticker']: h.get('score', 50) for h in todos_hs}

    # Agrupa por setor usando cache de fundamentos
    setores: dict = {}

    for ticker, dados in CACHE_FUNDAMENTOS.items():
        # Filtra por universo
        if universo == "BR" and not ticker.endswith(".SA"):
            continue
        if universo == "US" and ticker.endswith(".SA"):
            continue

        setor_raw = dados.get('setor') or '—'
        if not setor_raw or setor_raw == '—':
            continue

        setor = traduzir_setor(setor_raw)
        score = hs_map.get(ticker)
        if score is None:
            continue

        if setor not in setores:
            setores[setor] = {
                'setor':   setor,
                'ativos':  [],
                'scores':  [],
            }

        setores[setor]['ativos'].append(ticker)
        setores[setor]['scores'].append(score)

    # Calcula métricas por setor
    resultado = []
    for setor, dados_s in setores.items():
        scores = dados_s['scores']
        if not scores:
            continue

        score_medio = round(sum(scores) / len(scores), 1)
        score_max   = max(scores)
        score_min   = min(scores)
        n_acum      = sum(1 for s in scores if s >= 65)
        n_reduzir   = sum(1 for s in scores if s < 40)
        n_ativos    = len(scores)

        # Sinal do setor
        if score_medio >= 65:
            sinal = "acumulação"
            cor   = "#00C853"
        elif score_medio >= 45:
            sinal = "neutro"
            cor   = "#FF9900"
        else:
            sinal = "cautela"
            cor   = "#FF1744"

        resultado.append({
            'setor':        setor,
            'score_medio':  score_medio,
            'score_max':    score_max,
            'score_min':    score_min,
            'n_ativos':     n_ativos,
            'n_acumulacao': n_acum,
            'n_reduzir':    n_reduzir,
            'sinal':        sinal,
            'cor':          cor,
            'tickers':      dados_s['ativos'][:8],  # top 8 para exibição
        })

    return sorted(resultado, key=lambda x: x['score_medio'], reverse=True)


@st.cache_data(ttl=1800, show_spinner=False)
def rodar_screener(
    universo:        str,
    pl_min:          float,
    pl_max:          float,
    pvp_max:         float,
    roe_min:         float,
    dy_min:          float,
    score_min:       int,
    piotroski_min:   int,
    apenas_acima_mm: bool,
) -> pd.DataFrame:
    """
    Filtra o universo de ativos usando o cache de fundamentos
    e os health scores já calculados.
    """
    if universo == 'b3':
        tickers = SCREENER_B3
    elif universo == 'fii':
        tickers = FII_TODOS
    else:
        tickers = SCREENER_US

    cache_fund  = get_todos_fundamentos_cache()
    health_data = {h['ticker']: h for h in get_health_scores()}

    resultados = []

    for ticker in tickers:
        t_base = mapear_ticker_base(ticker)
        fund   = cache_fund.get(ticker) or cache_fund.get(t_base) or {}
        health = health_data.get(ticker) or health_data.get(t_base) or {}

        if not fund and not health:
            continue

        pl      = fund.get('p/l')
        pvp     = fund.get('p/vp')
        roe     = fund.get('roe%')
        dy      = fund.get('dy%', 0) or 0
        margem  = fund.get('margem%')
        ev_ebit = fund.get('ev/ebitda')
        nome    = fund.get('nome', '—')
        setor   = fund.get('setor', '—')
        score   = health.get('score', 0) or 0

        # Score 0 = nunca calculado
        nao_calculado = (score == 0)

        # ── Filtro health score ──────────────────────────────────
        # Se score_min > 0 e o ativo nunca teve score calculado
        # (score == 0), exclui — 0 não é "ótimo", é "sem dados".
        if score_min > 0:
            if nao_calculado or score < score_min:
                continue

        # ── Filtros fundamentalistas ─────────────────────────────
        # Regra: se o usuário definiu o filtro E o dado é None,
        # exclui o ativo. Dado ausente ≠ filtro aprovado.
        algum_filtro_fund = (
            pl_min > 0 or pl_max > 0 or
            pvp_max > 0 or roe_min > 0 or dy_min > 0
        )

        if pl_min > 0 or pl_max > 0:
            if pl is None:
                continue
            if pl_min > 0 and pl < pl_min:
                continue
            if pl_max > 0 and pl > pl_max:
                continue

        if pvp_max > 0:
            if pvp is None:
                continue
            if pvp > pvp_max:
                continue

        if roe_min > 0:
            if roe is None:
                continue
            if roe < roe_min:
                continue

        if dy_min > 0:
            if dy is None or dy < dy_min:
                continue

        # Se nenhum filtro fundamentalista foi definido mas o ativo
        # não tem nenhum dado, ainda inclui (com flag sem_dados)
        sem_dados_fund = (
            pl is None and pvp is None and
            roe is None and (dy == 0 or dy is None)
        )

        resultados.append({
            'ticker':        ticker.replace('.SA', ''),
            'nome':          nome[:30] if nome else '—',
            'setor':         setor[:25] if setor else '—',
            'p/l':           pl,
            'p/vp':          pvp,
            'roe%':          roe,
            'dy%':           dy if dy else None,
            'margem%':       margem,
            'ev/ebitda':     ev_ebit,
            'score':         score,
            '_nao_calc':     nao_calculado,
            '_sem_dados':    sem_dados_fund,
            '_ticker_full':  ticker,
        })

    if not resultados:
        return pd.DataFrame()

    df = pd.DataFrame(resultados)
    df = df.sort_values('score', ascending=False)
    return df


# 6. interface de separadores (tabs)
tab_momentum, tab_screener, tab_setorial = st.tabs([
    "📈 Momentum (Força Relativa)",
    "🎯 Screener Quantitativo",
    "🗺️ rotação setorial",
])

# ==========================================
# tab 1 — momentum screener
# ==========================================
with tab_momentum:
    section_title("🚀 momentum screener — força relativa")

    status_card(
        "metodologia",
        "score de momentum de 0 a 100 baseado em 6 critérios: retorno 1y, 6m, 3m e 1m (positivo = ponto), preço acima da MM50 e MM200. ativos com score alto têm momentum técnico consistente em múltiplas janelas.",
        tipo="info"
    )

    mc1, mc2, mc3 = st.columns([3, 2, 2])
    with mc1:
        mom_universos = st.multiselect(
            "universo:",
            ["🇧🇷 b3 — ações", "🌎 eua — ações", "🏢 b3 — fiis"],
            default=["🇧🇷 b3 — ações"],
            key="mom_universos"
        )
    with mc2:
        mom_top_n = st.slider("top N ativos:", 5, 30, 15, 5, key="mom_top_n")
    with mc3:
        st.markdown("<br>", unsafe_allow_html=True)
        btn_momentum = st.button("🚀 calcular momentum", type="primary", use_container_width=True, config={'responsive': True})

    score_minimo = st.slider("score mínimo de momentum:", 0, 100, 50, 10, key="mom_score_min")

    if btn_momentum:
        mom_lista = []
        if "🇧🇷 b3 — ações" in mom_universos: mom_lista += SCREENER_B3
        if "🌎 eua — ações" in mom_universos: mom_lista += SCREENER_US
        if "🏢 b3 — fiis" in mom_universos: mom_lista += FII_TODOS

        if not mom_lista:
            st.warning("selecione pelo menos um universo.")
        else:
            with st.spinner(f"calculando momentum de {len(mom_lista)} ativos..."):
                resultados_mom = calcular_momentum(tuple(mom_lista))
                df_mom = pd.DataFrame(resultados_mom)
                if not df_mom.empty:
                    df_mom = df_mom[df_mom['score momentum'] >= score_minimo]
                    df_mom = df_mom.head(mom_top_n)
                    st.session_state['momentum_resultado'] = df_mom

    if 'momentum_resultado' in st.session_state and not st.session_state['momentum_resultado'].empty:
        df_m = st.session_state['momentum_resultado']

        section_title(f"top {len(df_m)} ativos por momentum")

        mm1, mm2, mm3 = st.columns(3)
        with mm1:
            metric_card("melhor momentum", df_m.iloc[0]['ticker'], f"score {df_m.iloc[0]['score momentum']}/100", "bull")
        with mm2:
            metric_card("retorno médio 1y", f"{df_m['ret 1y (%)'].mean():.1f}%", "", "bull" if df_m['ret 1y (%)'].mean() > 0 else "bear")
        with mm3:
            acima_200 = (df_m['acima mm200'] == '✅').sum()
            metric_card("acima da mm200", f"{acima_200}/{len(df_m)}", "tendência de alta", "bull" if acima_200 > len(df_m)//2 else "amber")

        cols_mostrar = ['ticker', 'nome', 'setor', 'ret 1m (%)', 'ret 3m (%)', 'ret 6m (%)', 'ret 1y (%)', 'dist. topo 52w (%)', 'acima mm50', 'acima mm200', 'score momentum']

        def colorir_momentum(val):
            if isinstance(val, (int, float)):
                if val > 0: return 'color: #00C853'
                if val < 0: return 'color: #FF1744'
            return ''

        st.dataframe(
            df_m[cols_mostrar].style
                .map(colorir_momentum, subset=['ret 1m (%)', 'ret 3m (%)', 'ret 6m (%)', 'ret 1y (%)', 'dist. topo 52w (%)'])
                .format({'ret 1m (%)': '{:+.2f}%', 'ret 3m (%)': '{:+.2f}%', 'ret 6m (%)': '{:+.2f}%', 'ret 1y (%)': '{:+.2f}%', 'dist. topo 52w (%)': '{:+.2f}%', 'score momentum': '{:.0f}'}),
            use_container_width=True,
            hide_index=True
        )

        section_title("📊 mapa de retornos por janela temporal")

        fig_mom = go.Figure()
        janelas = ['ret 1m (%)', 'ret 3m (%)', 'ret 6m (%)', 'ret 1y (%)']
        labels = ['1 mês', '3 meses', '6 meses', '1 ano']

        for _, row in df_m.head(10).iterrows():
            fig_mom.add_trace(go.Scatter(
                x=labels,
                y=[row[j] for j in janelas],
                mode='lines+markers',
                name=row['ticker'],
                line=dict(width=1.5),
                hovertemplate=f"{row['ticker']}<br>%{{x}}: %{{y:+.1f}}%<extra></extra>"
            ))

        fig_mom.add_hline(y=0, line_color="#333", line_dash="dash", line_width=1)
        fig_mom.update_layout(**base_layout(height=400, title="retorno acumulado por janela — top 10 ativos"))
        st.plotly_chart(fig_mom, use_container_width=True, config={'responsive': True})

        st.markdown("---")

        col_a1, col_a2 = st.columns(2)
        with col_a1:
            for _, row in df_m.iterrows():
                c1, c2, c3 = st.columns([2, 3, 2])
                c1.markdown(f"**{row['ticker']}**")
                score = row['score momentum']
                cor_score = "#00C853" if score >= 70 else ("#FF9900" if score >= 40 else "#FF1744")
                barra = "█" * int(score // 10) + "░" * int(10 - score // 10)
                c2.markdown(f'<span style="font-family:Courier New; font-size:0.8rem; color:{cor_score};">{barra}</span>', unsafe_allow_html=True)
                if c3.button("＋ watchlist", key=f"btn_wl_mom_{row['ticker']}", use_container_width=True, config={'responsive': True}):
                    mercado = "brasil" if mapear_ticker_base(row['ticker']).endswith('.SA') else "eua"
                    modal_salvar_screener(row['ticker'], row['nome'], mercado)

        with col_a2:
            if st.button("🧠 ia: analisar momentum e identificar líderes setoriais", type="primary", use_container_width=True, config={'responsive': True}):
                with st.spinner("deepseek analisando momentum..."):
                    _dados_mom = df_m[cols_mostrar].head(10).to_csv(index=False)
                    chamar_ia(
                        prompt_usuario=(
                            f"dados de momentum:\n{_dados_mom}\n\n"
                            "responda em 4 bullet points curtos em português, letra minúscula:\n"
                            "1. qual ativo tem o momentum mais consistente e por quê.\n"
                            "2. quais setores estão liderando o movimento.\n"
                            "3. algum ativo próximo do topo de 52 semanas que pode estar em breakout.\n"
                            "4. riscos: algum ativo com momentum positivo mas fundamentos fracos."
                        ),
                        system      = SYSTEM_ANALISTA,
                        max_tokens  = 500,
                        temperatura = 0.3,
                        stream      = True,
                    )

# ==========================================
# tab 2 — screener quantitativo
# ==========================================
with tab_screener:
    section_title("🕵️ screener quantitativo — filtros paramétricos")

    # ── seleção de universo ──────────────────────────────────────────────────
    col_univ, col_info_scr = st.columns([2, 3])
    with col_univ:
        universo_sel = st.radio(
            "universo de ativos:",
            options=['b3', 'fii', 'us'],
            format_func=lambda x: {
                'b3':  f'🇧🇷 Ações B3 ({len(SCREENER_B3)} ativos)',
                'fii': f'🏢 FIIs ({len(FII_TODOS)} fundos)',
                'us':  f'🇺🇸 Ações EUA ({len(SCREENER_US)} ativos)',
            }[x],
            horizontal=True,
            key="screener_univ",
        )
    with col_info_scr:
        status_card(
            "como funciona",
            "os dados são do cache de fundamentos atualizado pelos botões de sync no topo da página. "
            "health score integra fatores técnicos, fundamentalistas e macro. "
            "use o botão 🔄 sync antes de rodar o screener pela primeira vez.",
            tipo="info",
        )

    st.markdown("---")

    # ══ BOTÕES DE PRESET E RESET ════════════════════════════════════════════
    section_title("⚙️ filtros")

    col_p1, col_p2, col_p3 = st.columns([1, 1, 4])
    with col_p1:
        if st.button("💎 valor", key="btn_preset_valor",
                     use_container_width=True, help="P/L baixo + ROE alto"):
            st.session_state["disc_pl_max_w"]  = 15.0
            st.session_state["disc_pl_min_w"]  = 0.0
            st.session_state["disc_roe_w"]     = 12.0
            st.session_state["disc_score_w"]   = 55
            st.session_state["disc_dy_w"]      = 0.0
            st.session_state["disc_pvp_w"]     = 0.0
            st.rerun()
    with col_p2:
        if st.button("💰 dividendo", key="btn_preset_div",
                     use_container_width=True, help="DY alto + score ok"):
            st.session_state["disc_dy_w"]      = 6.0
            st.session_state["disc_score_w"]   = 45
            st.session_state["disc_pl_max_w"]  = 0.0
            st.session_state["disc_pl_min_w"]  = 0.0
            st.session_state["disc_roe_w"]     = 0.0
            st.session_state["disc_pvp_w"]     = 0.0
            st.rerun()
    with col_p3:
        if st.button("↺ resetar filtros", key="btn_reset_filtros",
                     use_container_width=True, config={'responsive': True}):
            for _k in ['disc_pl_min_w', 'disc_pl_max_w', 'disc_roe_w',
                       'disc_dy_w', 'disc_score_w', 'disc_pvp_w',
                       'disc_mm_w']:
                st.session_state.pop(_k, None)
            st.rerun()

    # ══ WIDGETS DE FILTRO (com value= persistente via session_state) ════════
    f1, f2, f3, f4 = st.columns(4)

    with f1:
        st.markdown(
            '<div style="font-family:Courier New; font-size:0.72rem; color:#555; '
            'text-transform:uppercase; letter-spacing:0.08em; margin-bottom:6px;">p/l (faixa)</div>',
            unsafe_allow_html=True,
        )
        pl_col1, pl_col2 = st.columns(2)
        with pl_col1:
            st.number_input(
                "mín", min_value=0.0, max_value=200.0,
                step=1.0, key="disc_pl_min_w",
                label_visibility="collapsed",
                value=st.session_state.get('disc_pl_min_w', 0.0),
            )
        with pl_col2:
            st.number_input(
                "máx", min_value=0.0, max_value=500.0,
                step=1.0, key="disc_pl_max_w",
                label_visibility="collapsed",
                value=st.session_state.get('disc_pl_max_w', 15.0),
            )
        st.caption("0 = sem limite")

    with f2:
        st.number_input(
            "p/vp máximo:", min_value=0.0, max_value=20.0,
            step=0.1, format="%.1f",
            key="disc_pvp_w", help="0 = sem filtro",
            value=st.session_state.get('disc_pvp_w', 0.0),
        )
        st.number_input(
            "roe mínimo (%):", min_value=0.0, max_value=100.0,
            step=1.0, key="disc_roe_w",
            value=st.session_state.get('disc_roe_w', 0.0),
        )

    with f3:
        st.number_input(
            "dividend yield mínimo (%):",
            min_value=0.0, max_value=30.0,
            step=0.5, format="%.1f",
            key="disc_dy_w",
            value=st.session_state.get('disc_dy_w', 0.0),
        )
        st.slider(
            "health score mínimo:",
            min_value=0, max_value=100,
            step=5, key="disc_score_w",
            value=st.session_state.get('disc_score_w', 50),
        )

    with f4:
        st.checkbox(
            "apenas acima da MM200",
            key="disc_mm_w",
            value=st.session_state.get('disc_mm_w', False),
        )

    # ══ LEITURA DOS VALORES (via session_state após render) ═══════════════════
    pl_min    = st.session_state["disc_pl_min_w"]
    pl_max    = st.session_state["disc_pl_max_w"]
    pvp_max   = st.session_state["disc_pvp_w"]
    roe_min   = st.session_state["disc_roe_w"]
    dy_min    = st.session_state["disc_dy_w"]
    score_min = st.session_state["disc_score_w"]
    apenas_mm = st.session_state["disc_mm_w"]

    # ══ BOTÃO RODAR ══════════════════════════════════════════════════════════
    if st.button("🔍 rodar screener", type="primary",
                 use_container_width=True, key="btn_rodar"):
        with st.spinner("filtrando universo de ativos..."):
            df_result = rodar_screener(
                universo        = universo_sel,
                pl_min          = pl_min,
                pl_max          = pl_max,
                pvp_max         = pvp_max,
                roe_min         = roe_min,
                dy_min          = dy_min,
                score_min       = score_min,
                piotroski_min   = 0,
                apenas_acima_mm = apenas_mm,
            )
        st.session_state["screener_resultado"] = df_result
        st.session_state["screener_universo"]  = universo_sel

    # ── resultados ───────────────────────────────────────────────────────────
    if 'screener_resultado' in st.session_state:
        df_res = st.session_state['screener_resultado']
        univ   = st.session_state.get('screener_universo', 'b3')

        st.markdown("---")

        if df_res.empty:
            empty_state(
                "🔍", "nenhum ativo encontrado",
                "tente relaxar os filtros ou mudar o universo.",
            )
        else:
            col_r1, col_r2, col_r3 = st.columns([2, 2, 1])
            with col_r1:
                section_title(f"📋 {len(df_res)} ativos encontrados")
            with col_r2:
                ordenar_por = st.selectbox(
                    "ordenar por:",
                    options=['score', 'dy%', 'roe%', 'p/l', 'p/vp'],
                    key="sc_ordem",
                )
                df_res = df_res.sort_values(
                    ordenar_por,
                    ascending=(ordenar_por in ['p/l', 'p/vp']),
                    na_position='last',
                )
            with col_r3:
                csv_scr = df_res.drop(
                    columns=['_ticker_full', '_nao_calc', '_sem_dados'],
                    errors='ignore',
                ).to_csv(index=False).encode('utf-8')
                st.download_button(
                    "📥 exportar CSV",
                    data=csv_scr,
                    file_name=f"screener_{univ}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="sc_download",
                )

            # ── PROBLEMA 4: aviso cache incompleto ──────────────
            ativos_sem_dados = int(df_res.get('_sem_dados', pd.Series(dtype=bool)).sum()) if '_sem_dados' in df_res.columns else 0
            if ativos_sem_dados > len(df_res) * 0.3:
                status_card(
                    "⚠️ cache de fundamentos incompleto",
                    f"{ativos_sem_dados} de {len(df_res)} ativos sem dados fundamentalistas. "
                    f"clique em '🔄 sync cache eua' no topo da página para atualizar os dados "
                    f"antes de rodar o screener.",
                    tipo="amber",
                )

            # ── Tabela principal ─────────────────────────────────
            cols_display = ['ticker', 'nome', 'health', 'p/l', 'p/vp', 'roe%', 'dy%', 'margem%']
            df_display   = df_res[['ticker', 'nome', 'score', 'p/l', 'p/vp', 'roe%', 'dy%', 'margem%']].copy()

            # PROBLEMA 3: Barra de health como texto (evita cor invertida do ProgressColumn)
            df_display.insert(2, 'health', df_res['score'].apply(
                lambda s: (
                    f"{'█' * (int(s) // 10)}{'░' * (10 - int(s) // 10)} {int(s)}"
                    if s and s > 0 else "— n/c"
                )
            ))
            df_display = df_display.drop(columns=['score'])

            for col in ['p/l', 'p/vp', 'roe%', 'dy%', 'margem%']:
                if col in df_display.columns:
                    df_display[col] = df_display[col].apply(
                        lambda x: f"{x:.1f}" if pd.notna(x) and x is not None else "—"
                    )

            st.dataframe(
                df_display,
                use_container_width=True,
                hide_index=True,
                column_config={
                    'ticker': st.column_config.TextColumn("Ticker", width="small"),
                    'nome':   st.column_config.TextColumn("Nome",   width="medium"),
                    'health': st.column_config.TextColumn("Health Score", width="medium"),
                    'p/l':    st.column_config.TextColumn("P/L",   width="small"),
                    'p/vp':   st.column_config.TextColumn("P/VP",  width="small"),
                    'roe%':   st.column_config.TextColumn("ROE %", width="small"),
                    'dy%':    st.column_config.TextColumn("DY %",  width="small"),
                    'margem%':st.column_config.TextColumn("Margem %", width="small"),
                },
            )

            # ── adicionar à watchlist ────────────────────────────────────────
            section_title("➕ adicionar à watchlist")

            tickers_full = df_res['_ticker_full'].tolist()
            tickers_sel  = st.multiselect(
                "selecione ativos para adicionar:",
                options=tickers_full,
                format_func=lambda x: x.replace('.SA', ''),
                key="sc_add_wl",
            )

            if tickers_sel:
                if st.button(
                    f"➕ adicionar {len(tickers_sel)} ativo(s) à watchlist",
                    type="primary", key="sc_btn_add_wl",
                ):
                    _cache_scr = get_todos_fundamentos_cache()
                    try:
                        _wl_id = get_watchlist_padrao()
                    except Exception:
                        _wl_id = None

                    adicionados = 0
                    for t_add in tickers_sel:
                        t_add_base = mapear_ticker_base(t_add)
                        fund_t     = _cache_scr.get(t_add) or _cache_scr.get(t_add_base) or {}
                        mercado    = 'Brasil (B3)' if t_add.endswith('.SA') else 'EUA'
                        ok = adicionar_ativo(
                            ticker       = t_add,
                            nome         = fund_t.get('nome', t_add),
                            mercado      = mercado,
                            watchlist_id = _wl_id,
                        )
                        if ok:
                            adicionados += 1

                    if adicionados > 0:
                        st.success(f"✅ {adicionados} ativo(s) adicionados à watchlist!")
                        st.rerun()

with tab_setorial:
    section_title("🗺️ rotação setorial — health score médio por setor")

    st.markdown(
        '<div style="font-family:Courier New; font-size:0.75rem; '
        'color:#555; margin-bottom:16px; line-height:1.6;">'
        'score médio dos ativos de cada setor no universo analisado. '
        'setores verdes (≥65) em fase de acumulação. '
        'vermelhos (<40) em cautela. dados baseados nos health scores '
        'calculados pelo motor quantitativo.'
        '</div>',
        unsafe_allow_html=True,
    )

    _col_univ, _col_refresh = st.columns([3, 1])
    with _col_univ:
        _univ_set = st.radio(
            "universo:",
            ["BR", "US"],
            format_func=lambda x: {
                "BR": "🇧🇷 Brasil (B3 + FIIs)",
                "US": "🇺🇸 EUA (S&P500)",
            }[x],
            horizontal=True,
            key="radio_univ_setorial",
        )
    with _col_refresh:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 recalcular", key="btn_refresh_setorial",
                     use_container_width=True, config={'responsive': True}):
            st.cache_data.clear()
            st.rerun()

    with st.spinner("agrupando setores..."):
        _dados_set = calcular_heatmap_setorial(_univ_set)

    if not _dados_set:
        st.info(
            "nenhum dado setorial disponível. "
            "rode o sync de fundamentos no topo da página primeiro."
        )
    else:
        _n_acum_total  = sum(1 for s in _dados_set if s['sinal'] == 'acumulação')
        _n_neutro_total = sum(1 for s in _dados_set if s['sinal'] == 'neutro')
        _n_caut_total  = sum(1 for s in _dados_set if s['sinal'] == 'cautela')

        _rs1, _rs2, _rs3, _rs4 = st.columns(4)
        with _rs1:
            metric_card("setores analisados", str(len(_dados_set)), "com dados suficientes")
        with _rs2:
            metric_card("em acumulação", str(_n_acum_total),
                        "score médio ≥ 65", "bull" if _n_acum_total > 0 else "muted")
        with _rs3:
            metric_card("neutros", str(_n_neutro_total), "score 45–64", "amber")
        with _rs4:
            metric_card("em cautela", str(_n_caut_total),
                        "score médio < 45", "bear" if _n_caut_total > 0 else "muted")

        st.markdown("<br>", unsafe_allow_html=True)

        import plotly.graph_objects as go

        _setores_nomes  = [d['setor'] for d in _dados_set]
        _scores_medios  = [d['score_medio'] for d in _dados_set]
        _cores_barras   = [d['cor'] for d in _dados_set]
        _hover_texts    = [
            f"<b>{d['setor']}</b><br>"
            f"score médio: {d['score_medio']}<br>"
            f"ativos: {d['n_ativos']}<br>"
            f"acumulação: {d['n_acumulacao']} | cautela: {d['n_reduzir']}<br>"
            f"range: {d['score_min']} – {d['score_max']}<br>"
            f"tickers: {', '.join([t.replace('.SA','') for t in d['tickers']])}"
            for d in _dados_set
        ]

        _fig_set = go.Figure()

        _fig_set.add_trace(go.Bar(
            x=_scores_medios,
            y=_setores_nomes,
            orientation='h',
            marker_color=_cores_barras,
            marker_opacity=0.85,
            text=[f"{s:.0f}" for s in _scores_medios],
            textposition='outside',
            textfont=dict(size=10, color='#aaa', family='Courier New'),
            hovertext=_hover_texts,
            hoverinfo='text',
            name='score médio',
        ))

        _fig_set.add_vline(
            x=65, line_color="#00C853", line_dash="dash",
            line_width=1, annotation_text="acumulação",
            annotation_font_color="#00C853",
            annotation_font_size=9,
        )
        _fig_set.add_vline(
            x=40, line_color="#FF1744", line_dash="dash",
            line_width=1, annotation_text="cautela",
            annotation_font_color="#FF1744",
            annotation_font_size=9,
        )

        _h_set = max(300, len(_dados_set) * 38)
        _lay_set = base_layout(
            height=_h_set,
            title=f"health score médio por setor — {_univ_set}"
        )
        _lay_set.update(
            xaxis=dict(range=[0, 110], showgrid=True,
                       gridcolor='#2A2C3E', title='score médio'),
            yaxis=dict(showgrid=False, title=''),
            margin=dict(l=180, r=60, t=40, b=20),
        )
        _fig_set.update_layout(**_lay_set)
        st.plotly_chart(_fig_set, use_container_width=True, config={'responsive': True})

        st.markdown("<br>", unsafe_allow_html=True)
        section_title("detalhamento por setor")

        for _ds in _dados_set:
            _exp_label = (
                f"{_ds['setor']} — "
                f"score {_ds['score_medio']:.0f} | "
                f"{_ds['n_ativos']} ativos | "
                f"{_ds['sinal'].upper()}"
            )
            with st.expander(_exp_label, expanded=False):
                _dc1, _dc2, _dc3, _dc4 = st.columns(4)
                _dc1.metric("score médio",   f"{_ds['score_medio']:.1f}")
                _dc2.metric("melhor score",  f"{_ds['score_max']:.0f}")
                _dc3.metric("pior score",    f"{_ds['score_min']:.0f}")
                _dc4.metric("n° de ativos",  str(_ds['n_ativos']))

                st.markdown(
                    "**ativos com dados:** "
                    + " · ".join([
                        t.replace('.SA', '') for t in _ds['tickers']
                    ]),
                )