import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import datetime
from google import genai
import logging
import time

# silenciar alertas vermelhos do yahoo finance no terminal
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# importações do ecossistema finapp
from utils.auth import require_auth, render_user_badge
from utils.style import aplicar_tema
from utils.tickers import BRASIL_TODOS, XSTOCKS_TODOS, BR_INDICES, get_opcoes_selectbox, ticker_from_label, mapear_ticker_base
from database.db import registrar_decisao, listar_decisoes, atualizar_resultado, get_pesos, listar_watchlist, salvar_peso, get_health_scores, listar_watchlists, criar_portfolio, listar_portfolios, get_portfolio_padrao, definir_portfolio_padrao, deletar_portfolio

# componentes do design system
from utils.components import page_header, section_title, metric_card, status_card, empty_state, inject_keyboard_shortcuts
from utils.formatters import fmt_preco, fmt_pct, fmt_numero
from utils.charts import base_layout

# 1. configuração da página
st.set_page_config(page_title="terminal finapp | portfolio", layout="wide", page_icon="💼")

# 2. barreira de segurança multi-usuário
if not require_auth():
    st.stop()

# 3. renderizações pós-login
render_user_badge()
aplicar_tema()
inject_keyboard_shortcuts()

page_header("💼 gestão de portfólio", "visão consolidada da sua carteira, backtesting e diário de decisões.")

@st.cache_data(ttl=3600, show_spinner=False)
def calcular_betas(tickers_tuple: tuple) -> dict:
    """Calcula beta de cada ativo contra IBOV e S&P500 usando 1 ano de dados."""
    tickers = list(tickers_tuple)
    betas = {}
    try:
        benchmarks = ["^BVSP", "^GSPC"]
        todos = list(set([mapear_ticker_base(t) for t in tickers] + benchmarks))
        hist = yf.download(todos, period="1y", auto_adjust=True, progress=False)['Close']
        if isinstance(hist, pd.Series):
            hist = hist.to_frame()
        rets = hist.pct_change().dropna()

        for t in tickers:
            t_base = mapear_ticker_base(t)
            if t_base not in rets.columns:
                betas[t] = {'beta_ibov': 1.0, 'beta_sp': 1.0, 'is_br': t.endswith('.SA')}
                continue

            is_br = t.endswith('.SA')
            benchmark = "^BVSP" if is_br else "^GSPC"

            if benchmark in rets.columns:
                cov = rets[[t_base, benchmark]].dropna().cov()
                var_bench = rets[benchmark].var()
                beta = cov.loc[t_base, benchmark] / var_bench if var_bench > 0 else 1.0
                beta = max(min(beta, 3.0), -1.0)
            else:
                beta = 1.0

            betas[t] = {
                'beta_ibov': round(beta, 2) if is_br else round(beta * 0.3, 2),
                'beta_sp': round(beta * 0.3, 2) if is_br else round(beta, 2),
                'is_br': is_br
            }
    except:
        for t in tickers:
            betas[t] = {'beta_ibov': 1.0, 'beta_sp': 1.0, 'is_br': t.endswith('.SA')}

    return betas

# 4. criação das tabs
tab_posicoes, tab_stress, tab_backtest, tab_diario = st.tabs([
    "💼 posições & p&l",
    "⚡ stress test",
    "📊 backtesting",
    "📝 diário de decisões"
])

# ==========================================
# tab 1: posições e p&l
# ==========================================
with tab_posicoes:

    portfolios_lista = listar_portfolios()
    if not portfolios_lista:
        criar_portfolio("principal", icone="💼", cor="#FF9900")
        portfolios_lista = listar_portfolios()

    col_sel, col_btn = st.columns([4, 1])
    with col_sel:
        portfolio_idx = st.selectbox(
            "portfólio ativo:",
            range(len(portfolios_lista)),
            format_func=lambda i: f"{portfolios_lista[i]['icone']} {portfolios_lista[i]['nome']} ({portfolios_lista[i]['total_ativos']} ativos)",
            key="sel_portfolio_ativo"
        )
    portfolio_ativo = portfolios_lista[portfolio_idx]
    portfolio_id_ativo = portfolio_ativo['id']

    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("⚙️ gerenciar", use_container_width=True, key="btn_gerenciar_portfolio"):
            st.session_state['show_portfolio_manager'] = not st.session_state.get('show_portfolio_manager', False)

    if st.session_state.get('show_portfolio_manager', False):
        with st.expander("⚙️ gerenciar portfólios", expanded=True):
            st.markdown("##### criar novo portfólio")
            with st.form("form_novo_portfolio", clear_on_submit=True):
                fc1, fc2, fc3 = st.columns(3)
                with fc1:
                    novo_pf_nome = st.text_input("nome:", placeholder="ex: ações EUA")
                with fc2:
                    novo_pf_icone = st.selectbox("ícone:", ["💼", "🇧🇷", "🇺🇸", "🏢", "📈", "₿", "🌍"])
                with fc3:
                    novo_pf_cor = st.selectbox("cor:", ["#FF9900", "#00C853", "#00B0FF", "#E040FB", "#FF1744"])
                if st.form_submit_button("criar portfólio", type="primary"):
                    if novo_pf_nome.strip():
                        criar_portfolio(novo_pf_nome.strip(), icone=novo_pf_icone, cor=novo_pf_cor)
                        st.success(f"✅ portfólio '{novo_pf_nome}' criado!")
                        st.rerun()
                    else:
                        st.warning("digite um nome para o portfólio.")
            st.markdown("---")
            st.markdown("##### portfólios existentes")
            for pf in portfolios_lista:
                pc1, pc2, pc3 = st.columns([4, 1, 1])
                pc1.markdown(f"{pf['icone']} **{pf['nome']}** — {pf['total_ativos']} ativos")
                if pf['padrao']:
                    pc2.markdown('<span class="badge badge-amber">padrão</span>', unsafe_allow_html=True)
                else:
                    if pc2.button("⭐ padrão", key=f"pf_pad_{pf['id']}", use_container_width=True):
                        definir_portfolio_padrao(pf['id'])
                        st.rerun()
                if pc3.button("🗑️ excluir", key=f"pf_del_{pf['id']}", use_container_width=True, disabled=(len(portfolios_lista) <= 1)):
                    deletar_portfolio(pf['id'])
                    st.rerun()

    watchlist = listar_watchlist()
    pesos_atuais = {p['ticker']: p for p in get_pesos(portfolio_id=portfolio_id_ativo)}

    tickers_unicos = list(set([item['ticker'] for item in watchlist] + list(pesos_atuais.keys())))
    posicoes_ativas = []
    
    for t in tickers_unicos:
        p_atual = pesos_atuais.get(t, {})
        qtd = float(p_atual.get('quantidade', 0))
        if qtd > 0:
            pm = float(p_atual.get('preco_medio', 0))
            posicoes_ativas.append({
                "ticker": t,
                "quantidade": qtd,
                "preço médio": pm,
                "valor estimado": qtd * pm
            })
            
    if posicoes_ativas:
        section_title("📋 posições ativas")
        df_ativas = pd.DataFrame(posicoes_ativas)
        
        df_ativas_editado = st.data_editor(
            df_ativas,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            column_config={
                "ticker": st.column_config.TextColumn("ativo", disabled=True),
                "quantidade": st.column_config.NumberColumn("quantidade", min_value=0.0, step=0.001, format="%.4f"),
                "preço médio": st.column_config.NumberColumn("preço médio (R$/US$)", min_value=0.0, step=0.01, format="%.4f"),
                "valor estimado": st.column_config.NumberColumn("valor estimado", disabled=True, format="%.2f")
            }
        )
        
        patrimonio_estimado = (df_ativas_editado['quantidade'] * df_ativas_editado['preço médio']).sum()
        num_posicoes = len(df_ativas_editado[df_ativas_editado['quantidade'] > 0])
        
        c_txt, c_btn = st.columns([3, 1])
        with c_txt:
            st.markdown(f"<div style='font-family: Courier New; font-size: 0.85rem; color: #888; padding-top: 10px;'>patrimônio estimado: {fmt_preco(patrimonio_estimado, '$')} | {num_posicoes} posições ativas</div>", unsafe_allow_html=True)
        with c_btn:
            btn_salvar = st.button("💾 salvar alterações", type="primary", use_container_width=True)
            
        if btn_salvar:
            df_ativas_editado['valor total'] = df_ativas_editado['quantidade'] * df_ativas_editado['preço médio']
            patrimonio_total = df_ativas_editado['valor total'].sum()
            
            for _, row in df_ativas_editado.iterrows():
                t = row['ticker']
                qtd = row['quantidade']
                pm = row['preço médio']
                v_total = row['valor total']
                peso_real = (v_total / patrimonio_total) * 100 if (patrimonio_total > 0 and qtd > 0) else 0.0
                salvar_peso(t, peso_real, pm, qtd, portfolio_id=portfolio_id_ativo)
                
            st.success("✅ posições atualizadas.")
            st.rerun()
    else:
        empty_state("📋", "nenhuma posição ativa", "adicione sua primeira posição abaixo.")

    st.markdown("<hr style='margin: 1.5rem 0; opacity: 0.2;'>", unsafe_allow_html=True)
    section_title("➕ adicionar ou editar posição")
    
    with st.form("form_add_posicao", clear_on_submit=True):
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            opcoes_wl = [w['ticker'] for w in watchlist]
            ticker_sel = st.selectbox("ativo da watchlist", opcoes_wl, format_func=lambda x: x.lower()) if opcoes_wl else None
        with col_f2:
            qtd_form = st.number_input("quantidade", min_value=0.0, step=0.001, format="%.4f")
        with col_f3:
            pm_form = st.number_input("preço médio pago (R$/US$)", min_value=0.0, step=0.01, format="%.4f")
            
        ticker_manual_form = st.text_input("ou digite um ticker manualmente (sobrescreve seleção acima):", placeholder="ex: PETR4.SA ou AAPL").strip().upper()
        
        st.markdown("<br>", unsafe_allow_html=True)
        btn_add = st.form_submit_button("adicionar ao portfólio", type="primary", use_container_width=True)
        
        if btn_add:
            ticker_final = ticker_manual_form if ticker_manual_form else ticker_sel
            if ticker_final and qtd_form > 0 and pm_form > 0:
                salvar_peso(ticker_final, 0.0, pm_form, qtd_form, portfolio_id=portfolio_id_ativo)
                st.success(f"✅ {ticker_final} adicionado. salve as alterações para recalcular os pesos.")
                st.rerun()
            else:
                st.warning("preencha ticker, quantidade maior que zero e preço médio maior que zero.")

    ativos_alocados = {t: d for t, d in pesos_atuais.items() if d['peso'] > 0}
    
    if ativos_alocados:
        tickers_com_peso = list(ativos_alocados.keys())

        with st.spinner("a sincronizar cotações em tempo real para cálculo de p&l..."):
            live_data = {}
            for t in tickers_com_peso:
                t_base = mapear_ticker_base(t)
                try: 
                    hist = yf.Ticker(t_base).history(period="5d")['Close'].dropna()
                    if not hist.empty:
                        live_data[t] = float(hist.iloc[-1])
                    else:
                        live_data[t] = 0.0
                except: 
                    live_data[t] = 0.0

        st.markdown("---")
        section_title("📊 performance e distribuição")

        linhas_portfolio = []
        custo_total_carteira = 0.0
        valor_atual_carteira = 0.0
        
        health_raw = get_health_scores()
        health_data = {h['ticker']: h.get('score', 50) for h in health_raw}

        for t, dados in ativos_alocados.items():
            qtd = float(dados.get('quantidade', 0))
            pm = float(dados.get('preco_medio', 0))
            preco_atual = live_data.get(t, 0.0)
            custo_posicao = qtd * pm
            valor_posicao = qtd * preco_atual
            pnl_valor = valor_posicao - custo_posicao
            pnl_pct = (pnl_valor / custo_posicao * 100) if custo_posicao > 0 else 0.0
            
            custo_total_carteira += custo_posicao
            valor_atual_carteira += valor_posicao
            
            linhas_portfolio.append({
                "ativo": t, "qtd": qtd, "preço médio": pm, "preço atual": preco_atual,
                "custo total": custo_posicao, "valor atual": valor_posicao,
                "p&l ($)": pnl_valor, "p&l (%)": pnl_pct, "health score": health_data.get(mapear_ticker_base(t), "n/d")
            })

        df_portfolio = pd.DataFrame(linhas_portfolio)
        df_portfolio['peso atual (%)'] = (df_portfolio['valor atual'] / valor_atual_carteira) * 100 if valor_atual_carteira > 0 else 0.0

        pnl_global_valor = valor_atual_carteira - custo_total_carteira
        pnl_global_pct = (pnl_global_valor / custo_total_carteira * 100) if custo_total_carteira > 0 else 0.0

        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1: metric_card("custo total alocado", fmt_preco(custo_total_carteira, "$"))
        with col_m2: metric_card("património atual (m2m)", fmt_preco(valor_atual_carteira, "$"), fmt_pct(pnl_global_pct), "bull" if pnl_global_pct >= 0 else "bear")
        with col_m3: metric_card("p&l global", fmt_preco(pnl_global_valor, "$"), "", "bull" if pnl_global_valor >= 0 else "bear")

        st.markdown("<br>", unsafe_allow_html=True)

        def colorir_pnl(val):
            if pd.isna(val) or val == 0: return ''
            return 'color: #00C853; font-weight: bold;' if val > 0 else 'color: #FF1744; font-weight: bold;'

        st.dataframe(
            df_portfolio.style.map(colorir_pnl, subset=['p&l ($)', 'p&l (%)']).format({
                "qtd": "{:.4f}", "preço médio": "{:.4f}", "preço atual": "{:.2f}",
                "custo total": "{:,.2f}", "valor atual": "{:,.2f}", "p&l ($)": "{:+,.2f}",
                "p&l (%)": "{:+.2f}%", "peso atual (%)": "{:.2f}%"
            }),
            use_container_width=True, hide_index=True
        )
        
        st.markdown("<br>", unsafe_allow_html=True)
        csv = df_portfolio.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 exportar carteira (csv)",
            data=csv,
            file_name="portfolio_finapp.csv",
            mime="text/csv",
            use_container_width=True
        )

        st.markdown("<br>", unsafe_allow_html=True)
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            section_title("⚖️ alocação por ativo")
            fig_pie = go.Figure(go.Pie(labels=df_portfolio['ativo'], values=df_portfolio['valor atual'], hole=0.4, textinfo='label+percent', marker=dict(line=dict(color='#010101', width=2))))
            layout_pie = base_layout(height=350)
            if 'xaxis' in layout_pie:
                layout_pie['xaxis']['visible'] = False
            if 'yaxis' in layout_pie:
                layout_pie['yaxis']['visible'] = False
            fig_pie.update_layout(**layout_pie)
            st.plotly_chart(fig_pie, use_container_width=True)

        with col_g2:
            section_title("📈 p&l por ativo")
            df_pnl = df_portfolio.sort_values(by='p&l ($)', ascending=True)
            fig_bar = go.Figure(go.Bar(x=df_pnl['p&l ($)'], y=df_pnl['ativo'], orientation='h', marker_color=['#FF1744' if val < 0 else '#00C853' for val in df_pnl['p&l ($)']]))
            layout_bar = base_layout(height=350)
            if 'yaxis' in layout_bar:
                layout_bar['yaxis']['showgrid'] = False
            fig_bar.update_layout(**layout_bar)
            st.plotly_chart(fig_bar, use_container_width=True)

# ==========================================
# tab 2: stress test
# ==========================================
with tab_stress:
    section_title("⚡ stress test de portfólio")

    status_card(
        "metodologia",
        "simula o impacto de choques macro no portfólio usando betas históricos de cada ativo contra ibov e s&p500. o impacto é estimado como: variação_ativo = beta × choque_benchmark. os resultados são aproximações baseadas em comportamento histórico.",
        tipo="info"
    )

    ativos_stress = {t: d for t, d in {p['ticker']: p for p in get_pesos(portfolio_id=st.session_state.get('portfolio_id_stress', get_portfolio_padrao()))}.items() if d.get('quantidade', 0) > 0}

    if not ativos_stress:
        empty_state("⚡", "portfólio vazio", "adicione posições na aba posições & p&l para rodar o stress test.")
    else:
        st.markdown("---")
        section_title("⚙️ configurar cenários")

        cenarios_padrao = {
            "🔴 crise financeira severa": {"ibov": -35.0, "sp500": -40.0, "dolar": +35.0, "selic": +3.0},
            "🟠 recessão brasil": {"ibov": -20.0, "sp500": -5.0, "dolar": +20.0, "selic": +2.0},
            "🟡 aperto monetário fed": {"ibov": -10.0, "sp500": -15.0, "dolar": +10.0, "selic": +1.0},
            "🟢 pouso suave (bull case)": {"ibov": +15.0, "sp500": +12.0, "dolar": -8.0, "selic": -1.5},
            "✏️ cenário personalizado": None,
        }

        sc1, sc2 = st.columns([2, 3])
        with sc1:
            cenario_sel = st.selectbox("cenário macro:", list(cenarios_padrao.keys()), key="stress_cenario")

        with sc2:
            if cenarios_padrao[cenario_sel] is not None:
                c = cenarios_padrao[cenario_sel]
                st.markdown(f"""
                <div style="font-family:Courier New; font-size:0.82rem; color:#888; padding:8px; background:#0d0d0d; border-radius:4px; border-left:3px solid #FF9900;">
                IBOV: <span style="color:{'#FF1744' if c['ibov']<0 else '#00C853'}">{c['ibov']:+.1f}%</span> &nbsp;|&nbsp;
                S&P500: <span style="color:{'#FF1744' if c['sp500']<0 else '#00C853'}">{c['sp500']:+.1f}%</span> &nbsp;|&nbsp;
                Dólar: <span style="color:{'#FF1744' if c['dolar']<0 else '#00C853'}">{c['dolar']:+.1f}%</span> &nbsp;|&nbsp;
                Selic: <span style="color:{'#FF1744' if c['selic']<0 else '#00C853'}">{c['selic']:+.2f}pp</span>
                </div>
                """, unsafe_allow_html=True)
                choque_ibov = c['ibov']
                choque_sp = c['sp500']
            else:
                p1, p2 = st.columns(2)
                with p1:
                    choque_ibov = st.slider("ibov (%):", -60.0, 30.0, -20.0, 5.0, key="stress_ibov")
                    choque_dolar = st.slider("dólar (%):", -20.0, 50.0, 10.0, 5.0, key="stress_dolar")
                with p2:
                    choque_sp = st.slider("s&p500 (%):", -60.0, 30.0, -15.0, 5.0, key="stress_sp")
                    choque_selic = st.slider("selic (pp):", -3.0, 5.0, 1.0, 0.5, key="stress_selic")

        btn_stress = st.button("⚡ rodar stress test", type="primary", use_container_width=True)

        if btn_stress:
            with st.spinner("calculando betas e simulando cenários..."):
                tickers_stress = list(ativos_stress.keys())
                betas_calc = calcular_betas(tuple(tickers_stress))

                linhas_stress = []
                for t, dados in ativos_stress.items():
                    qtd = float(dados.get('quantidade', 0))
                    pm = float(dados.get('preco_medio', 0))
                    valor_pos = qtd * pm

                    beta_info = betas_calc.get(t, {'beta_ibov': 1.0, 'beta_sp': 1.0, 'is_br': t.endswith('.SA')})

                    if beta_info['is_br']:
                        impacto_pct = beta_info['beta_ibov'] * choque_ibov
                    else:
                        impacto_pct = beta_info['beta_sp'] * choque_sp

                    impacto_valor = valor_pos * (impacto_pct / 100)
                    valor_estressado = valor_pos + impacto_valor

                    linhas_stress.append({
                        'ticker': t,
                        'valor atual (R$)': round(valor_pos, 2),
                        'beta': beta_info['beta_ibov'] if beta_info['is_br'] else beta_info['beta_sp'],
                        'benchmark': 'ibov' if beta_info['is_br'] else 's&p500',
                        'impacto (%)': round(impacto_pct, 2),
                        'impacto (R$)': round(impacto_valor, 2),
                        'valor estressado (R$)': round(valor_estressado, 2),
                    })

                df_stress = pd.DataFrame(linhas_stress).sort_values('impacto (R$)')
                patrimonio_atual = df_stress['valor atual (R$)'].sum()
                patrimonio_stress = df_stress['valor estressado (R$)'].sum()
                impacto_total = patrimonio_stress - patrimonio_atual
                impacto_total_pct = (impacto_total / patrimonio_atual * 100) if patrimonio_atual > 0 else 0

                st.session_state['stress_resultado'] = df_stress
                st.session_state['stress_resumo'] = {
                    'patrimonio_atual': patrimonio_atual,
                    'patrimonio_stress': patrimonio_stress,
                    'impacto_total': impacto_total,
                    'impacto_total_pct': impacto_total_pct,
                    'cenario': cenario_sel
                }

        if 'stress_resultado' in st.session_state and 'stress_resumo' in st.session_state:
            df_s = st.session_state['stress_resultado']
            resumo = st.session_state['stress_resumo']

            st.markdown("---")
            section_title(f"📊 resultado — {resumo['cenario']}")

            cor_impacto = "bull" if resumo['impacto_total'] >= 0 else "bear"
            rc1, rc2, rc3 = st.columns(3)
            with rc1:
                metric_card("patrimônio atual", fmt_numero(resumo['patrimonio_atual'], "R$ "))
            with rc2:
                metric_card("patrimônio estressado", fmt_numero(resumo['patrimonio_stress'], "R$ "),
                           fmt_pct(resumo['impacto_total_pct']), cor_impacto)
            with rc3:
                metric_card("impacto total", fmt_numero(resumo['impacto_total'], "R$ "),
                           "perda estimada" if resumo['impacto_total'] < 0 else "ganho estimado", cor_impacto)

            def colorir_stress(val):
                if isinstance(val, (int, float)):
                    if val > 0: return 'color: #00C853'
                    if val < 0: return 'color: #FF1744'
                return ''

            st.dataframe(
                df_s.style
                    .applymap(colorir_stress, subset=['impacto (%)', 'impacto (R$)'])
                    .format({
                        'valor atual (R$)': 'R$ {:,.2f}',
                        'beta': '{:.2f}',
                        'impacto (%)': '{:+.2f}%',
                        'impacto (R$)': 'R$ {:+,.2f}',
                        'valor estressado (R$)': 'R$ {:,.2f}'
                    }),
                use_container_width=True,
                hide_index=True
            )

            fig_stress = go.Figure(go.Bar(
                x=df_s['impacto (R$)'],
                y=df_s['ticker'],
                orientation='h',
                marker_color=['#FF1744' if v < 0 else '#00C853' for v in df_s['impacto (R$)']],
                hovertemplate='%{y}<br>impacto: R$ %{x:+,.2f}<extra></extra>'
            ))
            fig_stress.add_vline(x=0, line_color="#333", line_width=1)
            fig_stress.update_layout(**base_layout(height=max(300, len(df_s) * 35 + 80), title="impacto por posição (R$)"))
            st.plotly_chart(fig_stress, use_container_width=True)

            if st.button("🧠 ia: recomendar proteções para este cenário", type="primary", use_container_width=True):
                with st.spinner("analisando exposições e gerando recomendações..."):
                    try:
                        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                        dados_texto = df_s.to_csv(index=False)
                        prompt = f"""você é um gestor de risco de um fundo multimercado brasileiro. analise o stress test abaixo e recomende ações defensivas.

cenário: {resumo['cenario']}
impacto total estimado: {resumo['impacto_total_pct']:+.1f}% (R$ {resumo['impacto_total']:+,.2f})

posições e impactos:
{dados_texto}

responda com 4 bullet points em português, letra minúscula:
1. qual posição representa o maior risco no cenário e por quê.
2. sugestão de hedge ou redução de exposição.
3. quais posições podem se beneficiar neste cenário (naturalmente defensivas).
4. recomendação de realocação para reduzir o impacto total em pelo menos 30%.

seja direto e objetivo."""
                        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                        status_card("recomendações de proteção — ia", response.text, tipo="info")
                    except Exception as e:
                        st.error(f"erro no agente de ia: {e}")

# ==========================================
# tab 3: backtesting
# ==========================================
with tab_backtest:
    
    if "bt_selecionados" not in st.session_state:
        st.session_state.bt_selecionados = ["ITUB4.SA", "VALE3.SA", "^BVSP", "^GSPC"]
        
    def carregar_portfolio():
        pesos = get_pesos()
        tkrs = [p['ticker'] for p in pesos if float(p.get('peso', 0)) > 0]
        if tkrs:
            st.session_state.bt_selecionados = list(dict.fromkeys(st.session_state.bt_selecionados + tkrs))
            
    def limpar_selecao():
        st.session_state.bt_selecionados = ["^BVSP", "^GSPC"]

    @st.dialog("👁️ importar de watchlists")
    def modal_importar_watchlists():
        wls = listar_watchlists()
        if not wls:
            st.info("nenhuma watchlist encontrada.")
            return

        opcoes = {f"{w['icone']} {w['nome']}": w['id'] for w in wls}
        selecionadas = st.multiselect("selecione as watchlists:", list(opcoes.keys()))

        if st.button("📥 confirmar importação", type="primary", use_container_width=True):
            if selecionadas:
                tkrs_importar = []
                for sel in selecionadas:
                    wl_id = opcoes[sel]
                    ativos_wl = listar_watchlist(watchlist_id=wl_id)
                    tkrs_importar.extend([a['ticker'] for a in ativos_wl])

                if tkrs_importar:
                    st.session_state.bt_selecionados = list(dict.fromkeys(st.session_state.get('bt_selecionados', []) + tkrs_importar))
                    st.success(f"✅ {len(tkrs_importar)} ativos importados com sucesso!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("as watchlists selecionadas estão vazias.")
            else:
                st.warning("selecione pelo menos uma watchlist para importar.")

    st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)
    cb1, cb2, cb3, cb4 = st.columns([2, 2, 2, 4])
    with cb1: 
        st.button("💼 importar portfólio", on_click=carregar_portfolio, use_container_width=True)
    with cb2: 
        if st.button("👁️ importar watchlist", use_container_width=True):
            modal_importar_watchlists()
    with cb3: 
        st.button("🧹 limpar ativos", on_click=limpar_selecao, use_container_width=True)

    c1, c2, c3 = st.columns([5, 2, 2])
    with c1:
        opcoes_base = BRASIL_TODOS + XSTOCKS_TODOS + BR_INDICES + ["^GSPC", "^IXIC", "^BVSP"]
        opcoes_bt = sorted(list(dict.fromkeys(opcoes_base + st.session_state.bt_selecionados)))
        
        selecionados = st.multiselect(
            "selecione os ativos e benchmarks:", 
            options=opcoes_bt, 
            key="bt_selecionados",
            format_func=lambda x: x.lower() 
        )
        ticker_extra = st.text_input("adicionar ticker não listado (opcional):", "").strip().upper()
        
        if ticker_extra and ticker_extra not in selecionados:
            selecionados = selecionados + [ticker_extra]

    with c2:
        periodo_opcoes = {"1 ano": "1y", "2 anos": "2y", "3 anos": "3y", "5 anos": "5y", "ytd": "ytd"}
        periodo_sel = st.selectbox("período:", list(periodo_opcoes.keys()), index=0)

    with c3:
        st.markdown("<br>", unsafe_allow_html=True)
        btn_calcular = st.button("calcular backtest", type="primary", use_container_width=True)

    if btn_calcular or selecionados:
        if not selecionados:
            st.warning("selecione pelo menos um ativo para iniciar a comparação.")
        else:
            with st.spinner("sincronizando séries históricas e ajustando proventos..."):
                try:
                    df_precos = pd.DataFrame()
                    for t in selecionados:
                        t_base = mapear_ticker_base(t)
                        try:
                            hist = yf.Ticker(t_base).history(period=periodo_opcoes[periodo_sel])['Close'].dropna()
                            if not hist.empty:
                                if hasattr(hist.index, 'tz') and hist.index.tz is not None:
                                    hist.index = hist.index.tz_localize(None)
                                df_precos[t] = hist
                        except: pass
                        
                    df_precos_exibicao = df_precos.dropna(how='all').ffill()

                    primeiro_preco = df_precos_exibicao.bfill().iloc[0]
                    df_norm = (df_precos_exibicao / primeiro_preco) * 100

                    fig = go.Figure()
                    cores_backtest = ["#FF9900", "#00B0FF", "#00C853", "#FF1744", "#E040FB", "#00BCD4", "#FFEB3B"]
                    
                    for i, coluna in enumerate(df_norm.columns):
                        retorno_total = df_norm[coluna].iloc[-1] - 100
                        cor_linha = cores_backtest[i % len(cores_backtest)]
                        fig.add_trace(go.Scatter(x=df_norm.index, y=df_norm[coluna], name=f"{coluna.lower()} ({retorno_total:+.2f}%)", mode='lines', line=dict(width=2, color=cor_linha), hovertemplate="<b>%{x}</b><br>base 100: %{y:.2f}<br>retorno: %{customdata:+.2f}%<extra></extra>", customdata=df_norm[coluna] - 100))

                    layout_bt = base_layout(height=550, title="performance acumulada (base 100)")
                    fig.update_layout(**layout_bt)
                    fig.add_hline(y=100, line_dash="dash", line_color="#333", opacity=0.8)

                    st.plotly_chart(fig, use_container_width=True)

                    section_title("resumo de performance no período")
                    cols_metrics = st.columns(len(selecionados))
                    for idx, col in enumerate(df_norm.columns):
                        retorno_final = df_norm[col].iloc[-1] - 100
                        cor_d = "bull" if retorno_final >= 0 else "bear"
                        with cols_metrics[idx % len(cols_metrics)]:
                            metric_card(col.lower(), fmt_pct(retorno_final), f"base 100: {df_norm[col].iloc[-1]:.2f}", cor_delta=cor_d)
                        
                    retornos = df_norm.pct_change().dropna()
                    metricas = {}
                    for col in retornos.columns:
                        total = (df_norm[col].iloc[-1] / 100) - 1
                        vol = retornos[col].std() * (252 ** 0.5) 
                        sharpe = (retornos[col].mean() * 252) / (retornos[col].std() * (252**0.5)) if vol > 0 else 0
                        max_dd_serie = (df_norm[col] / df_norm[col].cummax() - 1)
                        max_dd = max_dd_serie.min()
                        metricas[col.lower()] = {'retorno total %': f"{total*100:.2f}%", 'volatilidade anual %': f"{vol*100:.2f}%", 'sharpe ratio': f"{sharpe:.2f}", 'max drawdown %': f"{max_dd*100:.2f}%"}
                    
                    df_metricas = pd.DataFrame(metricas).T
                    st.markdown("---")
                    section_title("🧮 métricas de risco")
                    st.dataframe(df_metricas, use_container_width=True)
                except Exception as e:
                    st.error(f"erro ao calcular backtest: {str(e)}")

# ==========================================
# tab 3: diário de decisões
# ==========================================
with tab_diario:
    
    with st.expander("➕ registrar nova decisão", expanded=False):
        with st.form("form_decisao", clear_on_submit=True):
            c1, c2, c3 = st.columns([3, 2, 2])
            with c1:
                opcoes = get_opcoes_selectbox()
                selecao = st.selectbox("ativo:", opcoes, format_func=lambda x: x.lower())
                ticker_manual = st.text_input("ou digite o ticker manualmente:", "").strip().upper()
            with c2:
                tipo_decisao = st.selectbox("tipo de operação:", ['compra', 'venda', 'aumento posição', 'redução'])
                data_dec = st.date_input("data da decisão", datetime.date.today())
            with c3:
                preco_dec = st.number_input("preço na decisão (r$ / $):", min_value=0.0, format="%.2f")
                qtd_dec = st.number_input("quantidade:", min_value=0.0, format="%.4f")
                
            tese_dec = st.text_area("tese de investimento (por que comprou/vendeu? o que esperava?):", height=100)
            btn_salvar = st.form_submit_button("💾 registrar decisão", type="primary")
            
            if btn_salvar:
                ticker_final = ticker_manual if ticker_manual else ticker_from_label(selecao)
                if not ticker_final or not tese_dec or preco_dec <= 0:
                    st.error("preencha o ticker, o preço válido e a tese de investimento.")
                else:
                    registrar_decisao(ticker_final, tipo_decisao, data_dec.isoformat(), preco_dec, qtd_dec, tese_dec)
                    st.success("✅ decisão registrada com sucesso no seu diário de bordo!")
                    st.rerun()

    decisoes = listar_decisoes()
    if not decisoes:
        empty_state("📝", "diário vazio", "o seu diário de decisões está vazio. registre sua primeira operação acima.")
    else:
        st.markdown("---")
        with st.spinner("atualizando preços para auditar resultados..."):
            dados_tabela = []
            acertos = erros = neutros = total_avaliados = 0
            retornos_compra = []
            
            for d in decisoes:
                t = d['ticker']
                t_base = mapear_ticker_base(t)
                try: 
                    preco_atual = yf.Ticker(t_base).fast_info.last_price
                except: 
                    try:
                        preco_atual = float(yf.Ticker(t_base).history(period="1d")['Close'].iloc[-1])
                    except:
                        preco_atual = 0.0
                    
                retorno_pct = ((preco_atual / d['preco_decisao']) - 1) * 100 if d['preco_decisao'] and preco_atual else 0.0
                if d['tipo'] in ['venda', 'redução']: retorno_pct = -retorno_pct

                data_d = datetime.datetime.strptime(d['data_decisao'], "%Y-%m-%d").date()
                dias_passados = (datetime.date.today() - data_d).days
                
                res = d['resultado']
                if res == 'acerto': acertos += 1; total_avaliados += 1
                elif res == 'erro': erros += 1; total_avaliados += 1
                elif res == 'neutro': neutros += 1; total_avaliados += 1
                    
                if d['tipo'] == 'compra': retornos_compra.append(retorno_pct)
                    
                dados_tabela.append({'id': d['id'], 'ticker': t.lower(), 'tipo': d['tipo'], 'data': d['data_decisao'], 'preço decisão': d['preco_decisao'], 'preço atual': preco_atual, 'retorno %': retorno_pct, 'dias': dias_passados, 'tese': d['tese'][:50] + "..." if len(d['tese']) > 50 else d['tese'], 'resultado': res if res else '⏳ aguardando'})

        df_decisoes = pd.DataFrame(dados_tabela)

        section_title("📊 estatísticas de acerto (track record)")
        c_e1, c_e2, c_e3, c_e4 = st.columns(4)
        taxa_acerto = (acertos / total_avaliados * 100) if total_avaliados > 0 else 0
        retorno_medio_compra = sum(retornos_compra) / len(retornos_compra) if retornos_compra else 0
        melhor_decisao = df_decisoes['retorno %'].max() if not df_decisoes.empty else 0
        pior_decisao = df_decisoes['retorno %'].min() if not df_decisoes.empty else 0

        with c_e1: metric_card("taxa de acerto", f"{taxa_acerto:.1f}%", f"{total_avaliados} julgadas", "info")
        with c_e2: metric_card("retorno médio", fmt_pct(retorno_medio_compra), cor_delta="bull" if retorno_medio_compra >= 0 else "bear")
        with c_e3: metric_card("melhor decisão", fmt_pct(melhor_decisao), cor_delta="bull" if melhor_decisao >= 0 else "bear")
        with c_e4: metric_card("pior decisão", fmt_pct(pior_decisao), cor_delta="bull" if pior_decisao >= 0 else "bear")

        section_title("📜 histórico de operações")
        def formatar_tabela(val):
            if type(val) in [float, int]:
                color = '#00C853' if val > 0 else ('#FF1744' if val < 0 else '#888888')
                return f'color: {color}; font-weight: bold;'
            return ''

        st.dataframe(df_decisoes.drop(columns=['id']).style.map(formatar_tabela, subset=['retorno %']).format({'preço decisão': '{:.2f}', 'preço atual': '{:.2f}', 'retorno %': '{:+.2f}%'}), use_container_width=True, hide_index=True)

        with st.expander("⚖️ julgar uma decisão (atualizar status)"):
            c_u1, c_u2, c_u3 = st.columns([2, 2, 2])
            with c_u1: id_selecionado = st.selectbox("selecione o id da decisão:", df_decisoes['id'].tolist())
            with c_u2: novo_status = st.selectbox("veredicto:", ['acerto', 'erro', 'neutro', '⏳ aguardando'])
            with c_u3:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("atualizar resultado", type="primary", use_container_width=True):
                    status_db = None if novo_status == '⏳ aguardando' else novo_status
                    atualizar_resultado(id_selecionado, status_db)
                    st.success("julgamento atualizado!")
                    st.rerun()

        st.markdown("---")
        if st.button("🧠 ia: revisar padrões de decisão", type="primary"):
            with st.spinner("analisando vieses cognitivos e padrões comportamentais..."):
                try:
                    df_revisao = df_decisoes.head(10).drop(columns=['id'])
                    csv_dados = df_revisao.to_csv(index=False, float_format='%.2f')
                    
                    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                    prompt = f"""
                    você é um mentor de investimentos e analista comportamental. 
                    analise o histórico das últimas decisões do investidor abaixo:
                    
                    {csv_dados}
                    
                    inicie todas as frases e tópicos com letra minúscula. essa é a forma da nossa escrita.
                    1. **padrão de sucesso**: o que o investidor costuma fazer de certo nas decisões marcadas como "acerto"?
                    2. **padrão de erro**: o que costuma falhar nas decisões de "erro"?
                    3. **viés comportamental**: identifique o viés mais provável.
                    4. **plano de ação**: uma sugestão prática de melhoria.
                    """
                    resposta = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    status_card("mentoria comportamental ia", resposta.text, "info")
                except Exception as e:
                    st.error(f"falha ao conectar com o mentor de ia: {e}")