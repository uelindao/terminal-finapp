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
from database.db import registrar_decisao, listar_decisoes, atualizar_resultado, get_pesos, listar_watchlist, salvar_peso, get_health_scores, listar_watchlists

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

# 4. criação das tabs
tab_posicoes, tab_backtest, tab_diario = st.tabs([
    "💼 posições & p&l",
    "📊 backtesting",
    "📝 diário de decisões"
])

# ==========================================
# tab 1: posições e p&l
# ==========================================
with tab_posicoes:
    
    # nota: carrega a lista mestre (todas as watchlists) para preencher a planilha
    watchlist = listar_watchlist()
    pesos_atuais = {p['ticker']: p for p in get_pesos()}

    with st.expander("⚖️ composição do portfólio (planilha rápida)", expanded=True):
        
        dados_tabela = []
        for item in watchlist:
            t = item['ticker']
            p_atual = pesos_atuais.get(t, {})
            qtd = p_atual.get('quantidade')
            qtd = float(qtd) if qtd is not None else 0.0
            pm = p_atual.get('preco_medio')
            pm = float(pm) if pm is not None else 0.0
            dados_tabela.append({"ticker": t, "quantidade": qtd, "preço médio": pm})
            
        df_base = pd.DataFrame(dados_tabela)
        
        if not df_base.empty:
            df_editado = st.data_editor(
                df_base,
                use_container_width=True,
                hide_index=True,
                num_rows="fixed",
                column_config={
                    "ticker": st.column_config.TextColumn("ativo (watchlist)", disabled=True),
                    "quantidade": st.column_config.NumberColumn("quantidade atual", min_value=0.0, step=0.0001, format="%.4f"),
                    "preço médio": st.column_config.NumberColumn("preço médio pago ($/r$)", min_value=0.0, step=0.0001, format="%.4f")
                }
            )
            
            if st.button("💾 salvar e rebalancear", type="primary", use_container_width=True):
                df_editado['valor total'] = df_editado['quantidade'] * df_editado['preço médio']
                patrimonio_total = df_editado['valor total'].sum()
                
                for _, row in df_editado.iterrows():
                    t = row['ticker']
                    qtd = row['quantidade']
                    pm = row['preço médio']
                    peso_real = (row['valor total'] / patrimonio_total) * 100 if (patrimonio_total > 0 and qtd > 0) else 0.0
                    salvar_peso(t, peso_real, pm, qtd)
                    
                st.success("✅ portfólio atualizado! pesos calculados com precisão absoluta.")
                st.rerun()
        else:
            empty_state("⭐", "watchlist vazia", "adicione ativos no discovery ou na home primeiro para poder alocá-los.")

    ativos_alocados = {t: d for t, d in pesos_atuais.items() if d['peso'] > 0}
    
    if ativos_alocados:
        tickers_com_peso = list(ativos_alocados.keys())

        with st.spinner("a sincronizar cotações em tempo real para cálculo de p&l..."):
            live_data = {}
            try:
                # traduzimos os tickers para puxar do yahoo
                tickers_base = list(set([mapear_ticker_base(t) for t in tickers_com_peso]))
                hist = yf.download(tickers_base, period="5d", auto_adjust=True, progress=False)['Close']
                
                # blindagem contra o erro de tipo (series vs dataframe)
                if isinstance(hist, pd.Series): 
                    hist = hist.to_frame(name=tickers_base[0])
                hist = hist.ffill()
                
                # devolvemos o preço ao ticker rwa original
                for t in tickers_com_peso:
                    t_base = mapear_ticker_base(t)
                    try: live_data[t] = float(hist[t_base].dropna().iloc[-1])
                    except: live_data[t] = 0.0
            except Exception as e:
                st.error("erro ao transferir dados da bolsa.")

        st.markdown("---")
        section_title("📊 performance e distribuição")

        linhas_portfolio = []
        custo_total_carteira = 0.0
        valor_atual_carteira = 0.0
        
        # garante que os health scores são mapeados para a base também
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
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            section_title("⚖️ alocação por ativo")
            fig_pie = go.Figure(go.Pie(labels=df_portfolio['ativo'], values=df_portfolio['valor atual'], hole=0.4, textinfo='label+percent', marker=dict(line=dict(color='#010101', width=2))))
            layout_pie = base_layout(height=350)
            layout_pie['xaxis']['visible'] = False
            layout_pie['yaxis']['visible'] = False
            fig_pie.update_layout(**layout_pie)
            st.plotly_chart(fig_pie, use_container_width=True)

        with col_g2:
            section_title("📈 p&l por ativo")
            df_pnl = df_portfolio.sort_values(by='p&l ($)', ascending=True)
            fig_bar = go.Figure(go.Bar(x=df_pnl['p&l ($)'], y=df_pnl['ativo'], orientation='h', marker_color=['#FF1744' if val < 0 else '#00C853' for val in df_pnl['p&l ($)']]))
            layout_bar = base_layout(height=350)
            layout_bar['yaxis']['showgrid'] = False
            fig_bar.update_layout(**layout_bar)
            st.plotly_chart(fig_bar, use_container_width=True)

# ==========================================
# tab 2: backtesting
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
                    # traduzir os selecionados para o backtest
                    selecionados_base = list(set([mapear_ticker_base(t) for t in selecionados]))
                    dados_raw = yf.download(selecionados_base, period=periodo_opcoes[periodo_sel], auto_adjust=True, progress=False)
                    
                    df_precos = dados_raw['Close']
                    
                    # blindagem contra o erro de tipo (series vs dataframe)
                    if isinstance(df_precos, pd.Series):
                        df_precos = df_precos.to_frame(name=selecionados_base[0])

                    df_precos = df_precos.dropna(how='all').ffill()
                    
                    # reconstruir o dataframe com os nomes rwa originais
                    df_precos_exibicao = pd.DataFrame(index=df_precos.index)
                    for t in selecionados:
                        t_base = mapear_ticker_base(t)
                        if t_base in df_precos.columns:
                            df_precos_exibicao[t] = df_precos[t_base]

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
                try: preco_atual = yf.Ticker(t_base).fast_info.last_price
                except: preco_atual = 0.0
                    
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