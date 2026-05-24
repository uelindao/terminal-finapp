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
from utils.auth import require_auth, render_user_badge, render_painel_admin, get_current_user
from utils.style import aplicar_tema
from database.db import (
    init_db, popular_watchlist_inicial, listar_watchlist,
    remover_ativo, adicionar_ativo, atualizar_notas,
    get_health_scores, get_pesos,
    listar_watchlists, criar_watchlist, renomear_watchlist,
    deletar_watchlist, definir_watchlist_padrao, get_watchlist_padrao,
    registrar_envio_relatorio, get_ultimo_envio_relatorio, listar_relatorios_enviados
)
from utils.email_sender import enviar_relatorio_semanal
from utils.health_engine import calcular_health_score
from utils.tickers import mapear_ticker_base

from utils.components import (
    page_header, section_title, metric_card, 
    watchlist_card, empty_state, progress_steps, 
    status_card, inject_keyboard_shortcuts, auto_refresh_indicator
)
from utils.formatters import fmt_preco, fmt_pct

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

render_painel_admin()

with st.expander("👤 meu perfil", expanded=False):
    user = get_current_user()
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**usuário:** {user['username']}")
        st.markdown(f"**nome:** {user['nome'] or '—'}")
        st.markdown(f"**perfil:** {'administrador' if user['is_admin'] else 'usuário'}")
    with c2:
        with st.form("form_minha_senha", clear_on_submit=True):
            st.markdown("**alterar senha:**")
            senha_atual = st.text_input("senha atual:", type="password")
            senha_nova  = st.text_input("nova senha:", type="password")
            senha_conf  = st.text_input("confirmar:", type="password")

            if st.form_submit_button("alterar senha"):
                from database.db import autenticar_usuario, alterar_senha
                if autenticar_usuario(user['username'], senha_atual):
                    if senha_nova == senha_conf and len(senha_nova) >= 4:
                        alterar_senha(user['user_id'], senha_nova)
                        st.success("✅ senha alterada com sucesso!")
                    elif senha_nova != senha_conf:
                        st.error("as senhas não coincidem.")
                    else:
                        st.error("senha deve ter pelo menos 4 caracteres.")
                else:
                    st.error("senha atual incorreta.")

st.markdown("---")

# ==========================================
# NAVEGAÇÃO RÁPIDA
# ==========================================
section_title("🧭 navegação rápida")
c1, c2, c3, c4, c5 = st.columns(5)
with c1: st.page_link("pages/1_Research.py", label="micro (research)", icon="🔬")
with c2: st.page_link("pages/2_Discovery.py", label="oportunidades", icon="🎯")
with c3: st.page_link("pages/3_Macro.py", label="macro global", icon="🌍")
with c4: st.page_link("pages/4_Portfolio.py", label="meu portfólio", icon="💼")
with c5: st.page_link("pages/5_Solana.py", label="on-chain (rwa)", icon="⛓️")

st.markdown("---")

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

indices = buscar_indices_completo()
if indices:
    cols = st.columns(len(indices))
    for i, (nome, dados) in enumerate(indices.items()):
        cor_d = "bull" if dados['var'] >= 0 else "bear"
        sinal = "▲" if dados['var'] >= 0 else "▼"
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
            metric_card(
                label=nome,
                valor=valor_fmt,
                delta=f"{sinal} {abs(dados['var']):.2f}%",
                cor_delta=cor_d
            )

st.markdown("<br>", unsafe_allow_html=True)

# ==========================================
# FAIXA 2 — SEMÁFORO MACRO
# ==========================================
section_title("🚦 semáforo macro")

@st.cache_data(ttl=3600, show_spinner=False)
def buscar_dados_semaforo():
    dados = {"selic": None, "ipca": None, "t10y2y": None, "vix": None, "hy_spread": None}
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

cor_br, icone_br, texto_br = avaliar_semaforo_brasil(dados_sem.get("selic"), dados_sem.get("ipca"))
cor_us, icone_us, texto_us = avaliar_semaforo_eua(dados_sem.get("t10y2y"), dados_sem.get("vix"))
cor_risco, icone_risco, texto_risco = avaliar_semaforo_risco(dados_sem.get("vix"), dados_sem.get("hy_spread"))

cores_bg = {"bull": "#001a0d", "bear": "#1a0005", "amber": "#1a0f00"}
cores_border = {"bull": "#00C853", "bear": "#FF1744", "amber": "#FF9900"}

sm1, sm2, sm3 = st.columns(3)
with sm1:
    selic_txt = f"selic: {dados_sem['selic']:.1f}%" if dados_sem.get('selic') else "selic: n/d"
    ipca_txt = f"ipca: {dados_sem['ipca']:.2f}%" if dados_sem.get('ipca') else "ipca: n/d"
    st.markdown(f'''<div style="background:{cores_bg[cor_br]}; border:1px solid #1e1e1e; border-left:4px solid {cores_border[cor_br]}; border-radius:6px; padding:14px 16px;">
    <div style="font-family:Courier New; font-size:0.7rem; color:#555; text-transform:uppercase; letter-spacing:0.1em;">🇧🇷 brasil</div>
    <div style="font-family:Courier New; font-size:1.1rem; color:#E0E0E0; font-weight:bold; margin:6px 0;">{icone_br} {texto_br}</div>
    <div style="font-family:Courier New; font-size:0.78rem; color:#888;">{selic_txt} | {ipca_txt}</div>
    </div>''', unsafe_allow_html=True)
with sm2:
    t10_txt = f"yield curve: {dados_sem['t10y2y']:.2f}%" if dados_sem.get('t10y2y') is not None else "yield curve: n/d"
    vix_txt = f"vix: {dados_sem['vix']:.1f}" if dados_sem.get('vix') else "vix: n/d"
    st.markdown(f'''<div style="background:{cores_bg[cor_us]}; border:1px solid #1e1e1e; border-left:4px solid {cores_border[cor_us]}; border-radius:6px; padding:14px 16px;">
    <div style="font-family:Courier New; font-size:0.7rem; color:#555; text-transform:uppercase; letter-spacing:0.1em;">🇺🇸 eua</div>
    <div style="font-family:Courier New; font-size:1.1rem; color:#E0E0E0; font-weight:bold; margin:6px 0;">{icone_us} {texto_us}</div>
    <div style="font-family:Courier New; font-size:0.78rem; color:#888;">{t10_txt} | {vix_txt}</div>
    </div>''', unsafe_allow_html=True)
with sm3:
    hy_txt = f"spread hy: {dados_sem['hy_spread']:.2f}%" if dados_sem.get('hy_spread') else "spread hy: n/d"
    st.markdown(f'''<div style="background:{cores_bg[cor_risco]}; border:1px solid #1e1e1e; border-left:4px solid {cores_border[cor_risco]}; border-radius:6px; padding:14px 16px;">
    <div style="font-family:Courier New; font-size:0.7rem; color:#555; text-transform:uppercase; letter-spacing:0.1em;">🌐 risco global</div>
    <div style="font-family:Courier New; font-size:1.1rem; color:#E0E0E0; font-weight:bold; margin:6px 0;">{icone_risco} {texto_risco}</div>
    <div style="font-family:Courier New; font-size:0.78rem; color:#888;">{hy_txt} | {vix_txt}</div>
    </div>''', unsafe_allow_html=True)

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
    st.markdown(f"#### ativo: {ticker_nome.lower()}")
    
    cor_score = "#00C853" if score_final >= 70 else ("#FF9900" if score_final >= 40 else "#FF1744")
    st.markdown(f"<div style='font-size:2rem; font-family:Courier New; font-weight:bold; color:{cor_score}; text-align:center; padding:10px; background:#111; border-radius:8px; margin-bottom:20px;'>{score_final:.0f} / 100</div>", unsafe_allow_html=True)
    
    if breakdown_dict:
        st.markdown("**🧱 pilares de pontuação:**")
        for pilar, pts in breakdown_dict.items():
            if pts == 0 and "Penalidade" in pilar:
                continue 
            
            cor_pts = "#00C853" if pts > 0 else ("#FF1744" if pts < 0 else "#666")
            st.markdown(f"<div style='display:flex; justify-content:space-between; border-bottom:1px solid #222; padding:4px 0;'><span style='color:#ccc;'>{pilar.lower()}</span> <span style='color:{cor_pts}; font-family:Courier New; font-weight:bold;'>{pts:+.0f} pts</span></div>", unsafe_allow_html=True)
    else:
        st.info("💡 memorial não disponível. clique em '🚨 atualizar health scores' no topo da página para recalcular este ativo na nova versão.")
        
    if alertas_lista:
        st.markdown("<br>**🚨 contexto & alertas:**", unsafe_allow_html=True)
        for a in alertas_lista:
            st.markdown(f"<div style='font-size:0.8rem; color:#aaa; margin-bottom:4px; padding-left:10px; border-left:2px solid #444;'>{a}</div>", unsafe_allow_html=True)

# ── GRID DA WATCHLIST ATIVA ─────────────────────────────
watchlist = listar_watchlist(watchlist_id=watchlist_id_ativo)

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

    mercados = {}
    for item in watchlist:
        m = item['mercado']
        if m not in mercados:
            mercados[m] = []
        mercados[m].append(item)
        
    for mercado, ativos in mercados.items():
        st.markdown(f"##### 📍 {mercado.lower()}")
        cols = st.columns(4)
        for idx, item in enumerate(ativos):
            t = item['ticker']
            d = live_data.get(t, {'preco': 0.0, 'var_1d': 0.0, 'var_1m': 0.0})
            
            t_base = mapear_ticker_base(t)
            h_info = health_data.get(t_base, {'score': 50, 'alertas_venda': '{"alertas": [], "breakdown": {}}'})
            
            # DECODIFICAÇÃO ROBUSTA PROTEGIDA
            try: 
                raw_data = h_info['alertas_venda']
                parsed_data = json.loads(raw_data)
                
                # Se ainda for string (devido ao histórico corrompido de JSON duplo), decodifica novamente
                if isinstance(parsed_data, str):
                    parsed_data = json.loads(parsed_data)
                
                if isinstance(parsed_data, dict):
                    lista_alertas = parsed_data.get('alertas', [])
                    breakdown = parsed_data.get('breakdown', {})
                else:
                    lista_alertas = parsed_data if isinstance(parsed_data, list) else []
                    breakdown = {}
            except: 
                lista_alertas = []
                breakdown = {}

            with cols[idx % 4]:
                watchlist_card(
                    ticker=t, nome=item['nome'], preco=d['preco'], var_1d=d['var_1d'],
                    moeda="r$" if t_base.endswith(".SA") else "$",
                    health_score=h_info['score'], alertas=lista_alertas
                )
                
                # Botões de Ação do Card
                c1, c2, c3 = st.columns(3)
                with c1:
                    if st.button("🗑️", key=f"del_{t}", use_container_width=True, help="remover ativo"):
                        remover_ativo(t, watchlist_id=watchlist_id_ativo)
                        st.rerun()
                with c2:
                    nova_nota = st.popover("📝", use_container_width=True)
                    with nova_nota:
                        txt = st.text_area("anotações da tese:", value=item['notas'] or "", key=f"nota_{t}")
                        if st.button("salvar", key=f"btn_nota_{t}"):
                            atualizar_notas(t, txt, watchlist_id=watchlist_id_ativo)
                            st.rerun()
                with c3:
                    if st.button("🧮", key=f"calc_{t}", use_container_width=True, help="memorial de cálculo"):
                        exibir_memorial(t, h_info['score'], breakdown, lista_alertas)
                        
                st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)

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