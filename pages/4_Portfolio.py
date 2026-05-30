import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import datetime
import logging
import time

# silenciar alertas vermelhos do yahoo finance no terminal
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# importações do ecossistema finapp
from utils.auth import require_auth, render_user_badge
from utils.style import aplicar_tema
from utils.tickers import BRASIL_TODOS, XSTOCKS_TODOS, BR_INDICES, get_opcoes_selectbox, ticker_from_label, mapear_ticker_base
from database.db import registrar_decisao, listar_decisoes, atualizar_resultado, get_pesos, listar_watchlist, salvar_peso, get_health_scores, listar_watchlists, criar_portfolio, listar_portfolios, get_portfolio_padrao, definir_portfolio_padrao, deletar_portfolio, salvar_peso_alvo, get_pesos_alvo, deletar_peso_alvo, get_todos_fundamentos_cache, salvar_mensagem_chat, get_historico_chat, limpar_historico_chat

# componentes do design system
from utils.components import page_header, section_title, metric_card, status_card, empty_state, inject_keyboard_shortcuts
from utils.ai_client import chamar_ia, SYSTEM_PORTFOLIO
from utils.portfolio_importer import importar_planilha, TEMPLATE_CSV
from utils.formatters import fmt_preco, fmt_pct, fmt_numero
from utils.charts import base_layout
from utils.logger import get_logger

logger = get_logger(__name__)

# 1. barreira de segurança multi-usuário
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


@st.cache_data(ttl=3600, show_spinner=False)
def calcular_matriz_correlacao(tickers_tuple: tuple, periodo: str = "1y") -> dict:
    """
    Calcula matriz de correlação entre os ativos do portfólio.
    Retorna dict com:
      - 'matriz': pd.DataFrame com correlações
      - 'alertas': list[str] pares com correlação > 0.70
      - 'diversificacao_score': int 0-100
    """
    tickers = list(tickers_tuple)
    resultado = {'matriz': None, 'alertas': [], 'diversificacao_score': 50}

    if len(tickers) < 2:
        return resultado

    try:
        tickers_base = [mapear_ticker_base(t) for t in tickers]
        hist = yf.download(
            tickers_base,
            period=periodo,
            auto_adjust=True,
            progress=False,
        )['Close']

        if isinstance(hist, pd.Series):
            hist = hist.to_frame(name=tickers_base[0])

        # Remove timezone e normaliza
        if getattr(hist.index, 'tz', None) is not None:
            hist.index = hist.index.tz_localize(None)

        # Retornos diários
        rets = hist.pct_change().dropna()

        # Remove colunas com dados insuficientes
        rets = rets.dropna(axis=1, thresh=int(len(rets) * 0.7))

        if rets.shape[1] < 2:
            return resultado

        # Renomeia colunas para tickers originais
        mapa_reverso = {mapear_ticker_base(t): t for t in tickers}
        rets.columns = [mapa_reverso.get(c, c) for c in rets.columns]

        corr = rets.corr().round(2)
        resultado['matriz'] = corr

        # Alertas de alta correlação (pares > 0.70)
        alertas = []
        cols = corr.columns.tolist()
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                val = corr.iloc[i, j]
                if val > 0.70:
                    alertas.append(
                        f"{cols[i].replace('.SA','')} ↔ "
                        f"{cols[j].replace('.SA','')} — "
                        f"correlação {val:.2f} (alta)"
                    )
                elif val < -0.30:
                    alertas.append(
                        f"{cols[i].replace('.SA','')} ↔ "
                        f"{cols[j].replace('.SA','')} — "
                        f"correlação {val:.2f} (hedge natural)"
                    )
        resultado['alertas'] = alertas

        # Score de diversificação: 100 = correlação média próxima de 0
        # 0 = todos os ativos correlacionados > 0.9
        n = len(cols)
        if n > 1:
            vals_upper = [
                corr.iloc[i, j]
                for i in range(n)
                for j in range(i + 1, n)
            ]
            corr_media = float(np.mean(vals_upper)) if vals_upper else 0.5
            # Score: 0 de corr = 100 pts, 1.0 de corr = 0 pts
            score_div = int(max(0, min(100, (1 - corr_media) * 100)))
            resultado['diversificacao_score'] = score_div

    except Exception as e:
        logger.warning(f"[portfolio] correlação: {e}")

    return resultado


@st.cache_data(ttl=300, show_spinner=False)
def get_cambio_usd_brl() -> float:
    """Busca cotação atual do dólar via yfinance."""
    try:
        ticker_fx = yf.Ticker("BRL=X")
        hist_fx   = ticker_fx.history(period="1d")
        if not hist_fx.empty:
            return float(hist_fx['Close'].iloc[-1])
    except Exception as e:
        logger.warning(f"[portfolio] câmbio: {e}")
    return 5.80  # fallback

# 4. criação das tabs
tab_posicoes, tab_concentracao, tab_stress, tab_backtest, tab_diario, tab_ir, tab_chat = st.tabs([
    "💼 posições & p&l",
    "📊 concentração",
    "⚡ stress test",
    "📊 backtesting",
    "📝 diário de decisões",
    "🧾 imposto de renda",
    "💬 chat ia",
])

# variáveis partilhadas entre tabs — preenchidas em tab_posicoes
live_data: dict      = {}
ativos_alocados: dict = {}

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

    # Detecta troca de portfólio e limpa caches do chat
    _prev_portfolio_id = st.session_state.get('_prev_portfolio_id_chat')
    if _prev_portfolio_id and _prev_portfolio_id != portfolio_id_ativo:
        for _ck in ['chat_portfolio_contexto', 'chat_ctx_version',
                    'pesos_ativos_cache', 'live_data_cache',
                    'health_chat_cache', 'metricas_cache',
                    'chat_portfolio_msgs']:
            st.session_state.pop(_ck, None)
        st.session_state.pop(
            f"pesos_ativos_cache_{_prev_portfolio_id}", None
        )
    st.session_state['_prev_portfolio_id_chat'] = portfolio_id_ativo

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
        qtd = float(p_atual.get('quantidade') or 0)
        if qtd > 0:
            pm = float(p_atual.get('preco_medio') or 0)
            posicoes_ativas.append({
                "ticker": t,
                "quantidade": qtd,
                "preço médio": pm,
                "valor estimado": qtd * pm
            })
            
    # ══ IMPORTAÇÃO VIA PLANILHA ══════════════════════════════════════════════
    with st.expander("📥 importar portfólio via planilha", expanded=False):

        col_imp1, col_imp2 = st.columns([3, 1])
        with col_imp1:
            st.markdown(
                '<div style="font-family:Courier New; font-size:0.78rem; '
                'color:#555; line-height:1.6;">'
                '📋 <b>formato aceito:</b> CSV ou Excel com colunas '
                '<code>ticker</code>, <code>quantidade</code>, '
                '<code>preco_medio</code>.<br>'
                '💡 <b>dica:</b> envie prints da sua corretora para o Claude '
                'ou ChatGPT pedindo para gerar um CSV neste formato.</div>',
                unsafe_allow_html=True,
            )
        with col_imp2:
            st.download_button(
                label               = "📄 baixar template",
                data                = TEMPLATE_CSV,
                file_name           = "template_portfolio.csv",
                mime                = "text/csv",
                use_container_width = True,
                key                 = "dl_template_portfolio",
            )

        st.markdown("<br>", unsafe_allow_html=True)

        arquivo_imp = st.file_uploader(
            "selecione o arquivo:",
            type = ['csv', 'xlsx', 'xls'],
            key  = "uploader_portfolio",
            help = "CSV ou Excel com ticker, quantidade e preço médio",
        )

        if arquivo_imp is not None:
            resultado_imp = importar_planilha(
                arquivo_imp.read(), arquivo_imp.name
            )

            if resultado_imp['posicoes']:
                section_title(
                    f"✅ {len(resultado_imp['posicoes'])} posições detectadas "
                    f"— confirme antes de importar"
                )

                # ── Preview ──────────────────────────────────────────────
                df_prev = pd.DataFrame(resultado_imp['posicoes'])[
                    ['ticker', 'nome', 'quantidade', 'preco_medio', 'mercado']
                ].copy()
                df_prev['valor_estimado'] = (
                    df_prev['quantidade'] * df_prev['preco_medio']
                ).apply(lambda x: f"R$ {x:,.2f}")
                df_prev['preco_medio'] = df_prev['preco_medio'].apply(
                    lambda x: f"R$ {x:,.2f}"
                )
                st.dataframe(df_prev, use_container_width=True, hide_index=True)

                # Erros não-críticos como warnings
                for erro_imp in resultado_imp['erros']:
                    st.warning(f"⚠️ {erro_imp}")

                st.markdown("---")

                col_conf1, col_conf2, col_conf3 = st.columns(3)
                with col_conf1:
                    modo_import = st.radio(
                        "modo de importação:",
                        options=['adicionar', 'substituir'],
                        format_func=lambda x: {
                            'adicionar':  '➕ adicionar às posições atuais',
                            'substituir': '🔄 substituir portfólio inteiro',
                        }[x],
                        key="modo_importacao",
                    )

                with col_conf3:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button(
                        "✅ confirmar importação",
                        type="primary",
                        use_container_width=True,
                        key="btn_confirmar_import",
                    ):
                        from database.db import (
                            adicionar_ativo, get_watchlist_padrao,
                        )

                        wl_id_imp  = get_watchlist_padrao()
                        importados = 0
                        erros_imp  = []

                        for pos in resultado_imp['posicoes']:
                            try:
                                # Garante que o ativo existe na watchlist
                                adicionar_ativo(
                                    ticker       = pos['ticker'],
                                    nome         = pos['nome'],
                                    mercado      = pos['mercado'],
                                    watchlist_id = wl_id_imp,
                                )
                                # Salva posição no portfólio
                                salvar_peso(
                                    pos['ticker'],
                                    0.0,
                                    pos['preco_medio'],
                                    pos['quantidade'],
                                    portfolio_id=portfolio_id_ativo,
                                )
                                importados += 1
                            except Exception as e_pos:
                                erros_imp.append(
                                    f"{pos['ticker']}: {e_pos}"
                                )

                        if importados > 0:
                            st.success(
                                f"✅ {importados} posições importadas com sucesso!"
                            )
                            st.rerun()
                        for e_msg in erros_imp:
                            st.error(f"❌ {e_msg}")

            else:
                st.error("não foi possível detectar posições no arquivo.")
                for erro_imp in resultado_imp['erros']:
                    st.error(f"❌ {erro_imp}")
                st.info(
                    "💡 verifique se o arquivo tem as colunas: "
                    "ticker, quantidade, preco_medio"
                )

    # ══ TABELA DE POSIÇÕES ATIVAS ════════════════════════════════════════════
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
            btn_salvar = st.button("💾 salvar correções da tabela", type="primary", use_container_width=True)
            
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
    section_title("➕ lançar operação (compra / venda)")
    
    with st.form("form_add_posicao", clear_on_submit=True):
        col_op, col_f1, col_f2, col_f3 = st.columns([1, 2, 1, 1], gap="small")
        
        with col_op:
            tipo_op = st.radio("tipo de operação:", ["🟢 Comprar", "🔴 Vender"])
            
        with col_f1:
            opcoes_wl = [w['ticker'] for w in watchlist]
            ticker_sel = st.selectbox("ativo da watchlist", opcoes_wl, format_func=lambda x: x.lower()) if opcoes_wl else None
            
        with col_f2:
            qtd_form = st.number_input("quantidade operada", min_value=0.0, step=0.001, format="%.4f")
            
        with col_f3:
            pm_form = st.number_input("preço (R$/US$)", min_value=0.0, step=0.01, format="%.4f")
            
        ticker_manual_form = st.text_input("ou digite um ticker manualmente (sobrescreve seleção acima):", placeholder="ex: PETR4.SA ou AAPL").strip().upper()
        
        st.markdown("<br>", unsafe_allow_html=True)
        btn_add = st.form_submit_button("registrar operação no portfólio", type="primary", use_container_width=True)
        
        if btn_add:
            ticker_final = ticker_manual_form if ticker_manual_form else ticker_sel
            
            if ticker_final and qtd_form > 0 and pm_form > 0:
                # Obter dados atuais da posição antes da operação
                p_atual = pesos_atuais.get(ticker_final, {})
                qtd_atual = float(p_atual.get('quantidade') or 0)
                pm_atual = float(p_atual.get('preco_medio') or 0)
                
                if "Comprar" in tipo_op:
                    nova_qtd = qtd_atual + qtd_form
                    # Cálculo inteligente de Preço Médio
                    novo_pm = ((qtd_atual * pm_atual) + (qtd_form * pm_form)) / nova_qtd if nova_qtd > 0 else pm_form
                    
                    salvar_peso(ticker_final, 0.0, novo_pm, nova_qtd, portfolio_id=portfolio_id_ativo)
                    st.success(f"✅ compra de {qtd_form} cotas de {ticker_final} registrada! novo PM: {novo_pm:.2f}")
                    time.sleep(1.5)
                    st.rerun()
                    
                elif "Vender" in tipo_op:
                    if qtd_form > qtd_atual:
                        st.warning(f"⚠️ você está tentando vender {qtd_form} cotas, mas só possui {qtd_atual} de {ticker_final}.")
                    else:
                        nova_qtd = qtd_atual - qtd_form
                        # Em vendas, o Preço Médio das cotas restantes NÃO muda. Se zerar a posição, zera o PM.
                        novo_pm = pm_atual if nova_qtd > 0 else 0.0
                        
                        salvar_peso(ticker_final, 0.0, novo_pm, nova_qtd, portfolio_id=portfolio_id_ativo)
                        st.success(f"✅ venda de {qtd_form} cotas de {ticker_final} registrada com sucesso!")
                        time.sleep(1.5)
                        st.rerun()
            else:
                st.warning("preencha ticker, uma quantidade maior que zero e um preço válido.")

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
            qtd = float(dados.get('quantidade') or 0)
            pm = float(dados.get('preco_medio') or 0)
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

        # ── persiste dados para o chat IA (tab_chat usa estes) ──
        st.session_state['pesos_ativos_cache'] = [
            {
                'ticker':      row['ativo'],
                'quantidade':  row['qtd'],
                'preco_medio': row['preço médio'],
                'preco_atual': row['preço atual'],
                'valor':       row['valor atual'],
                'peso_pct':    row['peso atual (%)'],
                'pnl_pct':     row['p&l (%)'],
                'health_score': row['health score'],
            }
            for _, row in df_portfolio.iterrows()
        ]
        st.session_state['metricas_cache'] = {
            'valor_total':   valor_atual_carteira,
            'custo_total':   custo_total_carteira,
            'pnl_total_pct': pnl_global_pct,
            'num_posicoes':  len(df_portfolio),
        }

        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1: metric_card("custo total alocado", fmt_preco(custo_total_carteira, "$"), destaque=True)
        with col_m2: metric_card("património atual (m2m)", fmt_preco(valor_atual_carteira, "$"), fmt_pct(pnl_global_pct), "bull" if pnl_global_pct >= 0 else "bear", destaque=True)
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
            st.plotly_chart(fig_pie, use_container_width=True, config={'responsive': True})

        with col_g2:
            section_title("📈 p&l por ativo")
            df_pnl = df_portfolio.sort_values(by='p&l ($)', ascending=True)
            fig_bar = go.Figure(go.Bar(x=df_pnl['p&l ($)'], y=df_pnl['ativo'], orientation='h', marker_color=['#FF1744' if val < 0 else '#00C853' for val in df_pnl['p&l ($)']]))
            layout_bar = base_layout(height=350)
            if 'yaxis' in layout_bar:
                layout_bar['yaxis']['showgrid'] = False
            fig_bar.update_layout(**layout_bar)
            st.plotly_chart(fig_bar, use_container_width=True, config={'responsive': True})

        # ── VISÃO CONSOLIDADA POR MOEDA ──────────────────────────────────
        st.markdown("<br>", unsafe_allow_html=True)
        cambio_atual = get_cambio_usd_brl()

        posicoes_brl = []
        posicoes_usd = []

        for t, dados in ativos_alocados.items():
            qtd = float(dados.get('quantidade') or 0)
            pm  = float(dados.get('preco_medio') or 0)
            if qtd <= 0:
                continue

            t_base_moeda = mapear_ticker_base(t)
            eh_br        = t_base_moeda.endswith('.SA')
            preco_atual  = live_data.get(t, 0.0)

            if preco_atual <= 0:
                continue

            valor_atual  = preco_atual * qtd
            valor_custo  = pm * qtd
            pl_moeda     = valor_atual - valor_custo
            pl_pct       = ((valor_atual / valor_custo) - 1) * 100 if valor_custo > 0 else 0.0

            entry = {
                'ticker':          t,
                'qtd':             qtd,
                'pm':              pm,
                'preco_atual':     preco_atual,
                'valor_atual':     valor_atual,
                'valor_custo':     valor_custo,
                'pl_moeda':        pl_moeda,
                'pl_pct':          pl_pct,
                'moeda':           'BRL' if eh_br else 'USD',
                'valor_atual_brl': valor_atual if eh_br else valor_atual * cambio_atual,
                'valor_custo_brl': valor_custo if eh_br else valor_custo * cambio_atual,
                'pl_brl':          pl_moeda if eh_br else pl_moeda * cambio_atual,
            }

            if eh_br:
                posicoes_brl.append(entry)
            else:
                posicoes_usd.append(entry)

        if posicoes_brl or posicoes_usd:
            section_title("💰 visão consolidada por moeda")

            total_brl_carteira = (
                sum(p['valor_atual_brl'] for p in posicoes_brl) +
                sum(p['valor_atual_brl'] for p in posicoes_usd)
            )
            total_custo_brl = (
                sum(p['valor_custo_brl'] for p in posicoes_brl) +
                sum(p['valor_custo_brl'] for p in posicoes_usd)
            )
            pl_total_brl = total_brl_carteira - total_custo_brl
            pl_total_pct = ((total_brl_carteira / total_custo_brl) - 1) * 100 if total_custo_brl > 0 else 0.0

            total_usd  = sum(p['valor_atual'] for p in posicoes_usd)
            custo_usd  = sum(p['valor_custo'] for p in posicoes_usd)
            pl_usd     = total_usd - custo_usd
            pl_usd_pct = ((total_usd / custo_usd) - 1) * 100 if custo_usd > 0 else 0.0

            # contribuição cambial = diferença entre converter o P&L USD pelo câmbio atual
            # e o P&L BRL "real" das posições USD (custo em câmbio da época vs. câmbio hoje)
            pl_brl_posicoes_usd   = sum(p['pl_brl'] for p in posicoes_usd)
            pl_usd_em_brl_simples = pl_usd * cambio_atual
            contrib_cambio        = pl_brl_posicoes_usd - pl_usd_em_brl_simples

            cg1, cg2, cg3, cg4 = st.columns(4)
            with cg1:
                metric_card(
                    "patrimônio total (brl)",
                    f"R$ {total_brl_carteira:,.2f}",
                    f"custo: R$ {total_custo_brl:,.2f}",
                    cor_delta="info",
                )
            with cg2:
                cor_total = "bull" if pl_total_brl >= 0 else "bear"
                metric_card(
                    "p&l total em brl",
                    f"R$ {pl_total_brl:+,.2f}",
                    f"{pl_total_pct:+.2f}% sobre custo",
                    cor_delta=cor_total,
                )
            with cg3:
                cor_usd = "bull" if pl_usd >= 0 else "bear"
                metric_card(
                    "p&l ativos eua (usd)",
                    f"$ {pl_usd:+,.2f}",
                    f"{pl_usd_pct:+.2f}% | câmbio R$ {cambio_atual:.2f}",
                    cor_delta=cor_usd,
                )
            with cg4:
                cor_camb = "bull" if contrib_cambio >= 0 else "bear"
                metric_card(
                    "contribuição cambial",
                    f"R$ {contrib_cambio:+,.2f}",
                    "efeito usd/brl no resultado",
                    cor_delta=cor_camb,
                )

            st.markdown("---")
            col_br, col_us = st.columns(2)

            with col_br:
                section_title("🇧🇷 ativos brasileiros (brl)")
                total_br_val  = sum(p['valor_atual'] for p in posicoes_brl)
                total_br_cust = sum(p['valor_custo'] for p in posicoes_brl)
                pl_br         = total_br_val - total_br_cust
                pl_br_pct     = ((total_br_val / total_br_cust) - 1) * 100 if total_br_cust > 0 else 0.0

                st.markdown(
                    f'<div style="font-family:Courier New; font-size:0.85rem; margin-bottom:8px;">'
                    f'<span style="color:#555;">patrimônio: </span>'
                    f'<span style="color:#E0E0E0; font-weight:bold;">R$ {total_br_val:,.2f}</span> | '
                    f'<span style="color:#555;">p&l: </span>'
                    f'<span style="color:{"#00C853" if pl_br >= 0 else "#FF1744"}; font-weight:bold;">'
                    f'R$ {pl_br:+,.2f} ({pl_br_pct:+.1f}%)</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                for pos in sorted(posicoes_brl, key=lambda x: abs(x['pl_pct']), reverse=True):
                    cor_p = "#00C853" if pos['pl_pct'] >= 0 else "#FF1744"
                    st.markdown(
                        f'<div style="display:flex; justify-content:space-between; '
                        f'padding:4px 0; border-bottom:1px solid #111; '
                        f'font-family:Courier New; font-size:0.75rem;">'
                        f'<span style="color:#FF9900;">{pos["ticker"].replace(".SA","")}</span>'
                        f'<span style="color:#555;">R$ {pos["preco_atual"]:,.2f}</span>'
                        f'<span style="color:{cor_p};">{pos["pl_pct"]:+.1f}%</span>'
                        f'<span style="color:{cor_p};">R$ {pos["pl_moeda"]:+,.0f}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            with col_us:
                section_title("🇺🇸 ativos eua (usd + brl)")

                st.markdown(
                    f'<div style="font-family:Courier New; font-size:0.85rem; margin-bottom:8px;">'
                    f'<span style="color:#555;">em usd: </span>'
                    f'<span style="color:#E0E0E0; font-weight:bold;">$ {total_usd:,.2f}</span> | '
                    f'<span style="color:#555;">em brl: </span>'
                    f'<span style="color:#E0E0E0; font-weight:bold;">R$ {total_usd * cambio_atual:,.2f}</span>'
                    f'<br><span style="color:#555; font-size:0.65rem;">câmbio: R$ {cambio_atual:.4f}/USD</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                for pos in sorted(posicoes_usd, key=lambda x: abs(x['pl_pct']), reverse=True):
                    cor_p = "#00C853" if pos['pl_pct'] >= 0 else "#FF1744"
                    st.markdown(
                        f'<div style="display:flex; justify-content:space-between; '
                        f'padding:4px 0; border-bottom:1px solid #111; '
                        f'font-family:Courier New; font-size:0.75rem;">'
                        f'<span style="color:#FF9900;">{pos["ticker"].replace(".SA","")}</span>'
                        f'<span style="color:#555;">$ {pos["preco_atual"]:,.2f}</span>'
                        f'<span style="color:{cor_p};">{pos["pl_pct"]:+.1f}%</span>'
                        f'<span style="color:{cor_p}; font-size:0.68rem;">R$ {pos["pl_brl"]:+,.0f}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

        # ── rebalanceamento inteligente ───────────────────────────────────
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("⚖️ rebalanceamento inteligente", expanded=False):

            st.markdown(
                '<div style="font-family:Courier New; font-size:0.78rem; color:#555; margin-bottom:16px;">'
                'defina a alocação-alvo (%) para cada ativo e veja exatamente quanto '
                'comprar ou vender para rebalancear a carteira.</div>',
                unsafe_allow_html=True,
            )

            pesos_alvo_list = get_pesos_alvo(portfolio_id_ativo)
            pesos_alvo_dict = {p['ticker']: float(p['peso_alvo']) for p in pesos_alvo_list}

            if valor_atual_carteira <= 0:
                st.warning("adicione posições com quantidade e preço para usar o rebalanceamento.")
            else:
                # ── 1. definição dos alvos ────────────────────────────────────
                section_title("1. defina os pesos-alvo (%)")

                tickers_port = [
                    t for t, d in ativos_alocados.items()
                    if float(d.get('quantidade') or 0) > 0
                ]

                total_alvo  = 0.0
                novos_alvos = {}

                n_cols     = min(4, len(tickers_port))
                cols_alvo  = st.columns(n_cols) if n_cols > 0 else [st]
                for i, t in enumerate(tickers_port):
                    with cols_alvo[i % len(cols_alvo)]:
                        alvo_atual = pesos_alvo_dict.get(t, 0.0)
                        novo_alvo  = st.number_input(
                            f"{t.replace('.SA', '')}",
                            min_value=0.0, max_value=100.0,
                            value=float(alvo_atual),
                            step=1.0, format="%.1f",
                            key=f"alvo_{t}",
                        )
                        novos_alvos[t] = novo_alvo
                        total_alvo    += novo_alvo

                # Indicador de soma dos alvos
                cor_total = "#00C853" if abs(total_alvo - 100) < 0.1 else "#FF1744"
                aviso_soma = "✅" if abs(total_alvo - 100) < 0.1 else "⚠️ deve somar 100%"
                st.markdown(
                    f'<div style="font-family:Courier New; font-size:0.85rem; '
                    f'color:{cor_total}; margin:8px 0;">'
                    f'total alocado: {total_alvo:.1f}% {aviso_soma}</div>',
                    unsafe_allow_html=True,
                )

                col_s1, col_s2 = st.columns([1, 3])
                with col_s1:
                    if st.button("💾 salvar alvos", type="primary", use_container_width=True,
                                 key="btn_salvar_alvos"):
                        for t, alvo in novos_alvos.items():
                            salvar_peso_alvo(portfolio_id_ativo, t, alvo)
                        st.success("✅ alvos salvos!")
                        st.rerun()

                # ── 2. plano de rebalanceamento ───────────────────────────────
                if pesos_alvo_dict and abs(total_alvo - 100) < 5:

                    section_title("2. plano de rebalanceamento")

                    aporte_adicional = st.number_input(
                        "aporte adicional disponível (R$):",
                        min_value=0.0, value=0.0,
                        step=100.0, format="%.2f",
                        key="aporte_rebal",
                        help="valor extra que você quer aportar agora",
                    )

                    valor_total_novo = valor_atual_carteira + aporte_adicional

                    dados_rebal = []
                    for t, dados in ativos_alocados.items():
                        qtd_atual = float(dados.get('quantidade') or 0)
                        if qtd_atual <= 0:
                            continue

                        preco_at  = live_data.get(t, 0.0)
                        val_atual = qtd_atual * preco_at
                        pct_atual = (val_atual / valor_atual_carteira * 100
                                     if valor_atual_carteira > 0 else 0.0)

                        alvo_pct  = pesos_alvo_dict.get(t, 0.0)
                        val_alvo  = valor_total_novo * alvo_pct / 100
                        diferenca = val_alvo - val_atual
                        qtd_op    = diferenca / preco_at if preco_at > 0 else 0.0
                        desvio_pp = pct_atual - alvo_pct

                        dados_rebal.append({
                            'ticker':       t.replace('.SA', ''),
                            '_ticker_orig': t,
                            'peso atual':   f"{pct_atual:.1f}%",
                            'peso alvo':    f"{alvo_pct:.1f}%",
                            'desvio':       desvio_pp,
                            'valor atual':  val_atual,
                            'valor alvo':   val_alvo,
                            'diferença R$': diferenca,
                            'ação':         qtd_op,
                            'preço':        preco_at,
                        })

                    if dados_rebal:
                        dados_rebal.sort(key=lambda x: abs(x['desvio']), reverse=True)

                        for d in dados_rebal:
                            cor_op = "#00C853" if d['diferença R$'] > 0 else "#FF1744"
                            op_txt = "COMPRAR" if d['diferença R$'] > 0 else "VENDER"
                            seta   = "▲" if d['diferença R$'] > 0 else "▼"

                            r1, r2, r3, r4, r5 = st.columns([2, 2, 2, 3, 3], gap="small")
                            with r1:
                                st.markdown(
                                    f'<div style="font-family:Courier New; color:#FF9900; font-weight:bold;">{d["ticker"]}</div>'
                                    f'<div style="font-family:Courier New; font-size:0.7rem; color:#555;">{d["peso atual"]} → {d["peso alvo"]}</div>',
                                    unsafe_allow_html=True,
                                )
                            with r2:
                                cor_dev = ("#FF1744" if abs(d['desvio']) > 5
                                           else "#FF9900" if abs(d['desvio']) > 2
                                           else "#00C853")
                                st.markdown(
                                    f'<div style="font-family:Courier New; color:{cor_dev}; font-size:0.85rem;">'
                                    f'desvio: {d["desvio"]:+.1f}pp</div>',
                                    unsafe_allow_html=True,
                                )
                            with r3:
                                st.markdown(
                                    f'<div style="font-family:Courier New; color:#888; font-size:0.8rem;">'
                                    f'R$ {d["valor atual"]:,.0f} → R$ {d["valor alvo"]:,.0f}</div>',
                                    unsafe_allow_html=True,
                                )
                            with r4:
                                st.markdown(
                                    f'<div style="font-family:Courier New; color:{cor_op}; font-size:0.85rem; font-weight:bold;">'
                                    f'{seta} {op_txt} R$ {abs(d["diferença R$"]):,.2f}</div>',
                                    unsafe_allow_html=True,
                                )
                            with r5:
                                if d['preço'] > 0 and abs(d['ação']) >= 0.01:
                                    qtd_fmt = (
                                        f"{d['ação']:+.0f} cotas"
                                        if abs(d['ação']) >= 1
                                        else f"{d['ação']:+.4f} lotes"
                                    )
                                    st.markdown(
                                        f'<div style="font-family:Courier New; color:{cor_op}; font-size:0.8rem;">'
                                        f'{qtd_fmt} @ R$ {d["preço"]:,.2f}</div>',
                                        unsafe_allow_html=True,
                                    )

                            st.markdown(
                                '<div style="height:1px; background:#1e1e1e; margin:4px 0;"></div>',
                                unsafe_allow_html=True,
                            )

                        # Resumo
                        total_compras = sum(d['diferença R$'] for d in dados_rebal if d['diferença R$'] > 0)
                        total_vendas  = abs(sum(d['diferença R$'] for d in dados_rebal if d['diferença R$'] < 0))
                        aporte_liq    = max(0.0, total_compras - total_vendas)

                        st.markdown("---")
                        rc1, rc2, rc3 = st.columns(3)
                        with rc1:
                            metric_card("total a comprar",   f"R$ {total_compras:,.2f}", "", "bull")
                        with rc2:
                            metric_card("total a vender",    f"R$ {total_vendas:,.2f}",  "", "bear")
                        with rc3:
                            metric_card("aporte necessário", f"R$ {aporte_liq:,.2f}",
                                        "além do que já tem em carteira", "amber")

# ==========================================
# tab 2: concentração de risco
# ==========================================
with tab_concentracao:
    # ── CARREGA DADOS INDEPENDENTE DA ABA POSIÇÕES ────────────────────────
    _pesos_conc = st.session_state.get("pesos_ativos_cache", [])
    if not _pesos_conc:
        _pesos_conc = [p for p in get_pesos(portfolio_id=portfolio_id_ativo) if float(p.get('quantidade') or 0) > 0]
        st.session_state["pesos_ativos_cache"] = _pesos_conc

    # ── TENTA CARREGAR COTAÇÕES VIA CACHE OU YFINANCE ─────────────────────
    _live_conc = st.session_state.get("live_data_cache", {})
    if not _live_conc and _pesos_conc:
        _tickers_conc = list(set([
            _p['ticker'] for _p in _pesos_conc
        ]))
        try:
            _hist_c = yf.download(
                _tickers_conc, period="2d",
                auto_adjust=True, progress=False,
            )
            if isinstance(_hist_c.columns, pd.MultiIndex):
                _hist_c.columns = _hist_c.columns.get_level_values(0)
            _close_c = _hist_c.get('Close', _hist_c)
            for _tc in _tickers_conc:
                try:
                    if isinstance(_close_c, pd.DataFrame) and _tc in _close_c.columns:
                        _s = _close_c[_tc].dropna()
                    elif isinstance(_close_c, pd.Series):
                        _s = _close_c.dropna()
                    else:
                        continue
                    _live_conc[_tc] = {'preco': float(_s.iloc[-1])}
                except Exception:
                    _live_conc[_tc] = {'preco': 0.0}
            st.session_state["live_data_cache"] = _live_conc
        except Exception as _ec:
            logger.warning(f"[conc] cotações: {_ec}")

    section_title("🎯 análise de concentração de risco")

    # ── MONTA DADOS DE CONCENTRAÇÃO ──────────────────────────────────────
    _cache_fund = get_todos_fundamentos_cache()

    _total_cart = 0.0
    for _p in _pesos_conc:
        _qtd = float(_p.get('quantidade') or 0)
        _tb  = _p['ticker']
        _pr  = _live_conc.get(_tb, {}).get('preco', 0.0)
        # Fallback: usa preco_medio do banco se cotação live falhou
        if _pr <= 0:
            _pr = float(_p.get('preco_medio') or 0)
        _total_cart += _pr * _qtd

    if _total_cart <= 0:
        empty_state(
            "📊", "sem dados de posições",
            "adicione posições com quantidade e preço para ver a análise de concentração."
        )
    else:
        dados_conc = []

        for _p in _pesos_conc:
            _t   = _p['ticker']
            _qtd = float(_p.get('quantidade') or 0)
            if _qtd <= 0:
                continue

            _preco  = _live_conc.get(_t, {}).get('preco', 0.0)
            if _preco <= 0:
                _preco = float(_p.get('preco_medio') or 0)
            _valor  = _preco * _qtd
            _peso   = (_valor / _total_cart * 100) if _total_cart > 0 else 0.0

            _eh_br = _t.endswith('.SA')
            _moeda = 'BRL' if _eh_br else 'USD'
            _pais  = 'Brasil' if _eh_br else 'EUA'

            # setor — prioriza cache de fundamentos local
            _t_base = _t.replace('.SA', '')
            _fund_p = _cache_fund.get(_t, _cache_fund.get(_t_base, {}))
            _setor  = _fund_p.get('setor') or '—'
            if _setor in ('—', '', None):
                _setor = 'outros'

            dados_conc.append({
                'ticker': _t.replace('.SA', ''),
                'valor':  _valor,
                'peso':   _peso,
                'setor':  _setor.lower(),
                'pais':   _pais,
                'moeda':  _moeda,
                'eh_br':  _eh_br,
            })

        # ── ALERTAS DE CONCENTRAÇÃO ──────────────────────────────────────
        alertas_conc = []

        # por ativo (> 20 %)
        for _dc in dados_conc:
            if _dc['peso'] > 20:
                alertas_conc.append({
                    'tipo':  'ativo',
                    'msg':   f"⚠️ {_dc['ticker']} representa {_dc['peso']:.1f}% da carteira (limite sugerido: 20%)",
                    'nivel': 'bear' if _dc['peso'] > 30 else 'amber',
                })

        # por setor (> 40 %)
        setores_peso: dict[str, float] = {}
        for _dc in dados_conc:
            setores_peso[_dc['setor']] = setores_peso.get(_dc['setor'], 0.0) + _dc['peso']

        for _setor_k, _setor_v in setores_peso.items():
            if _setor_v > 40:
                alertas_conc.append({
                    'tipo':  'setor',
                    'msg':   f"⚠️ setor '{_setor_k}' representa {_setor_v:.1f}% da carteira (limite sugerido: 40%)",
                    'nivel': 'bear' if _setor_v > 55 else 'amber',
                })

        # por país (> 80 %)
        paises_peso: dict[str, float] = {}
        for _dc in dados_conc:
            paises_peso[_dc['pais']] = paises_peso.get(_dc['pais'], 0.0) + _dc['peso']

        for _pais_k, _pais_v in paises_peso.items():
            if _pais_v > 80:
                alertas_conc.append({
                    'tipo':  'pais',
                    'msg':   f"⚠️ {_pais_v:.1f}% da carteira concentrada em {_pais_k} — considere diversificação geográfica",
                    'nivel': 'amber',
                })

        # por moeda
        moedas_peso: dict[str, float] = {}
        for _dc in dados_conc:
            moedas_peso[_dc['moeda']] = moedas_peso.get(_dc['moeda'], 0.0) + _dc['peso']

        # exibe alertas
        if alertas_conc:
            for _alerta in alertas_conc:
                status_card(
                    f"concentração por {_alerta['tipo']}",
                    _alerta['msg'],
                    tipo=_alerta['nivel'],
                )
        else:
            status_card(
                "✅ concentração dentro dos limites",
                "nenhum ativo acima de 20%, nenhum setor acima de 40%. carteira bem diversificada.",
                tipo="bull",
            )

        # ── CARDS DE RESUMO ──────────────────────────────────────────────
        st.markdown("---")
        cc1, cc2, cc3, cc4 = st.columns(4)

        _maior = max(dados_conc, key=lambda x: x['peso'])
        _cor_ma = ("bear" if _maior['peso'] > 25 else
                   "amber" if _maior['peso'] > 15 else "bull")
        with cc1:
            metric_card(
                "maior posição",
                _maior['ticker'],
                f"{_maior['peso']:.1f}% da carteira",
                cor_delta=_cor_ma,
            )
        with cc2:
            metric_card(
                "nº de ativos",
                str(len(dados_conc)),
                "diversificação por ativo",
                cor_delta="info",
            )
        with cc3:
            _pct_brl = paises_peso.get('Brasil', 0.0)
            _pct_usd = paises_peso.get('EUA', 0.0)
            metric_card(
                "exposição brl / usd",
                f"{_pct_brl:.0f}% / {_pct_usd:.0f}%",
                "brasil vs eua",
                cor_delta="info",
            )
        with cc4:
            _hhi      = sum(_dc['peso'] ** 2 for _dc in dados_conc) / 10000
            _diversif = max(0.0, 100.0 - _hhi * 100)
            _cor_hhi  = ("bull" if _diversif > 70 else
                         "amber" if _diversif > 50 else "bear")
            metric_card(
                "índice de diversificação",
                f"{_diversif:.0f}/100",
                "baseado no HHI (100 = máx diversif.)",
                cor_delta=_cor_hhi,
            )

        # ── GRÁFICOS DE PIZZA ────────────────────────────────────────────
        st.markdown("---")

        _cores_pizza = [
            "#FF9900", "#00C853", "#00B0FF", "#FF1744", "#E040FB",
            "#FFD700", "#8B00FF", "#FF69B4", "#00BFFF", "#B87333",
            "#C0C0C0", "#90EE90", "#DEB887", "#6F4E37", "#F5F5DC",
            "#E5E4E2", "#FF8C00",
        ]

        def _pizza_chart(labels, values, title, height=290):
            _fig = go.Figure(go.Pie(
                labels=labels,
                values=values,
                hole=0.45,
                textinfo='label+percent',
                textfont=dict(family='Courier New', size=10, color='#888'),
                marker=dict(
                    colors=_cores_pizza[:len(labels)],
                    line=dict(color='#050505', width=2),
                ),
                hovertemplate='%{label}<br>%{value:.1f}%<extra></extra>',
            ))
            _layout = base_layout(height=height, title=title)
            _layout['showlegend'] = False
            _fig.update_layout(**_layout)
            return _fig

        _cg1, _cg2, _cg3 = st.columns(3)

        with _cg1:
            _labels_a = [_dc['ticker'] for _dc in dados_conc]
            _values_a = [_dc['peso']   for _dc in dados_conc]
            st.plotly_chart(
                _pizza_chart(_labels_a, _values_a, "por ativo"),
                use_container_width=True,
                config={'responsive': True},
            )

        with _cg2:
            _labels_s = list(setores_peso.keys())
            _values_s = list(setores_peso.values())
            st.plotly_chart(
                _pizza_chart(_labels_s, _values_s, "por setor"),
                use_container_width=True,
                config={'responsive': True},
            )

        with _cg3:
            _labels_m = list(moedas_peso.keys())
            _values_m = list(moedas_peso.values())
            st.plotly_chart(
                _pizza_chart(_labels_m, _values_m, "por moeda"),
                use_container_width=True,
                config={'responsive': True},
            )

        # ── MATRIZ DE CORRELAÇÃO ─────────────────────────────────────────
        st.markdown("<br>", unsafe_allow_html=True)
        section_title("🔗 matriz de correlação entre ativos")

        _tickers_corr = tuple([
            p['ticker'] for p in _pesos_conc
            if float(p.get('quantidade') or 0) > 0
        ])

        if len(_tickers_corr) < 2:
            st.info("adicione pelo menos 2 posições para calcular a correlação.")
        else:
            _periodo_corr = st.radio(
                "período de cálculo:",
                ["6mo", "1y", "2y"],
                format_func=lambda x: {"6mo": "6 meses", "1y": "1 ano", "2y": "2 anos"}[x],
                horizontal=True,
                key="radio_periodo_corr",
            )

            with st.spinner("calculando correlações..."):
                _res_corr = calcular_matriz_correlacao(_tickers_corr, _periodo_corr)

            _corr_df = _res_corr.get('matriz')
            _score_div = _res_corr.get('diversificacao_score', 50)
            _alertas_corr = _res_corr.get('alertas', [])

            if _corr_df is not None and not _corr_df.empty:

                # Cards de resumo
                _cc1, _cc2, _cc3 = st.columns(3)
                with _cc1:
                    _cor_div = (
                        "#00C853" if _score_div >= 60
                        else "#FF9900" if _score_div >= 35
                        else "#FF1744"
                    )
                    _label_div = (
                        "boa diversificação" if _score_div >= 60
                        else "diversificação moderada" if _score_div >= 35
                        else "alta concentração"
                    )
                    metric_card(
                        "score de diversificação",
                        f"{_score_div}/100",
                        _label_div,
                        "bull" if _score_div >= 60 else ("amber" if _score_div >= 35 else "bear"),
                    )
                with _cc2:
                    metric_card(
                        "pares de alta correlação",
                        str(sum(1 for a in _alertas_corr if "alta" in a)),
                        "> 0.70 — risco de concentração oculta",
                        "bear" if any("alta" in a for a in _alertas_corr) else "bull",
                    )
                with _cc3:
                    metric_card(
                        "hedges naturais",
                        str(sum(1 for a in _alertas_corr if "hedge" in a)),
                        "correlação < -0.30",
                        "bull" if any("hedge" in a for a in _alertas_corr) else "muted",
                    )

                st.markdown("<br>", unsafe_allow_html=True)

                # Heatmap de correlação
                _ticks = _corr_df.columns.tolist()
                _ticks_clean = [t.replace('.SA', '') for t in _ticks]
                _z = _corr_df.values.tolist()

                # Texto das células
                _text = [
                    [f"{_corr_df.iloc[i, j]:.2f}" for j in range(len(_ticks))]
                    for i in range(len(_ticks))
                ]

                _fig_corr = go.Figure(go.Heatmap(
                    z=_z,
                    x=_ticks_clean,
                    y=_ticks_clean,
                    text=_text,
                    texttemplate="%{text}",
                    textfont=dict(size=11, color='white', family='Courier New'),
                    colorscale=[
                        [0.0,  "#1565C0"],   # azul escuro — correlação negativa
                        [0.35, "#1a1a1a"],   # neutro — correlação zero
                        [0.65, "#1a1a1a"],   # neutro
                        [1.0,  "#B71C1C"],   # vermelho — correlação alta
                    ],
                    zmin=-1, zmax=1,
                    colorbar=dict(
                        title="correlação",
                        titlefont=dict(color="#888", size=10),
                        tickfont=dict(color="#888", size=9),
                        thickness=12,
                    ),
                    hovertemplate=(
                        "%{y} ↔ %{x}<br>"
                        "correlação: %{z:.2f}<extra></extra>"
                    ),
                ))

                _dim_corr = max(280, min(len(_ticks) * 55, 600))
                _lay_corr = base_layout(
                    height=_dim_corr,
                    title=f"correlação de retornos diários — {_periodo_corr}"
                )
                _lay_corr.update(
                    xaxis=dict(tickfont=dict(size=10, color='#aaa', family='Courier New')),
                    yaxis=dict(tickfont=dict(size=10, color='#aaa', family='Courier New')),
                    margin=dict(l=80, r=40, t=40, b=80),
                    autosize=True,
                )
                _fig_corr.update_layout(**_lay_corr)
                st.plotly_chart(_fig_corr, use_container_width=True, config={'responsive': True})

                # Alertas de correlação
                if _alertas_corr:
                    st.markdown(
                        '<div style="font-family:Courier New; font-size:0.72rem; '
                        'color:#555; margin-top:4px;">⚠️ pares críticos:</div>',
                        unsafe_allow_html=True,
                    )
                    for _ac in _alertas_corr:
                        _cor_ac = "#FF9900" if "alta" in _ac else "#00C853"
                        st.markdown(
                            f'<div style="font-family:Courier New; font-size:0.75rem; '
                            f'color:{_cor_ac}; padding:2px 0;">• {_ac}</div>',
                            unsafe_allow_html=True,
                        )

                # Interpretação IA
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button(
                    "🧠 ia: interpretar diversificação da carteira",
                    key="btn_ia_corr",
                    type="secondary",
                ):
                    _prompt_corr = (
                        f"portfólio com {len(_ticks)} ativos.\n\n"
                        f"score de diversificação: {_score_div}/100\n\n"
                        f"pares com alta correlação (> 0.70):\n"
                        + "\n".join([f"- {a}" for a in _alertas_corr if "alta" in a] or ["nenhum"])
                        + f"\n\npares com correlação negativa (hedge natural):\n"
                        + "\n".join([f"- {a}" for a in _alertas_corr if "hedge" in a] or ["nenhum"])
                        + f"\n\nativos: {', '.join(_ticks_clean)}\n\n"
                        "em 3 tópicos curtos (letra minúscula):\n"
                        "1. o portfólio está bem diversificado ou há concentração oculta?\n"
                        "2. quais pares representam o maior risco de correlação?\n"
                        "3. que tipo de ativo poderia melhorar a diversificação?"
                    )
                    _us_corr = st.session_state.get('user_settings', {})
                    chamar_ia(
                        prompt_usuario=_prompt_corr,
                        system=SYSTEM_PORTFOLIO,
                        max_tokens=400,
                        temperatura=0.3,
                        stream=True,
                        user_settings=_us_corr,
                    )
            else:
                st.warning("dados insuficientes para calcular correlação.")

# ==========================================
# tab 3: stress test
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
                    qtd = float(dados.get('quantidade') or 0)
                    pm = float(dados.get('preco_medio') or 0)
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
                    .map(colorir_stress, subset=['impacto (%)', 'impacto (R$)'])
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
            st.plotly_chart(fig_stress, use_container_width=True, config={'responsive': True})

            if st.button("🧠 ia: recomendar proteções para este cenário", type="primary", use_container_width=True):
                with st.spinner("deepseek analisando exposições..."):
                    _prompt_stress = (
                        f"cenário de stress: {resumo['cenario']}\n"
                        f"impacto total estimado: {resumo['impacto_total_pct']:+.1f}% "
                        f"(R$ {resumo['impacto_total']:+,.2f})\n\n"
                        f"posições e impactos:\n{df_s.to_csv(index=False)}\n\n"
                        "responda com 4 bullet points em português, letra minúscula:\n"
                        "1. qual posição representa o maior risco no cenário e por quê.\n"
                        "2. sugestão de hedge ou redução de exposição.\n"
                        "3. quais posições podem se beneficiar neste cenário (naturalmente defensivas).\n"
                        "4. recomendação de realocação para reduzir o impacto total em pelo menos 30%."
                    )
                    chamar_ia(
                        prompt_usuario = _prompt_stress,
                        system         = SYSTEM_PORTFOLIO,
                        max_tokens     = 600,
                        temperatura    = 0.3,
                        stream         = True,
                    )

# ==========================================
# tab 3: backtesting
# ==========================================
with tab_backtest:
    
    if "bt_selecionados" not in st.session_state:
        st.session_state.bt_selecionados = ["ITUB4.SA", "VALE3.SA", "^BVSP", "^GSPC"]
        
    def carregar_portfolio():
        pesos = get_pesos()
        tkrs = [p['ticker'] for p in pesos if float(p.get('peso') or 0) > 0]
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

                    st.plotly_chart(fig, use_container_width=True, config={'responsive': True})

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
            with st.spinner("deepseek analisando padrões comportamentais..."):
                try:
                    df_revisao = df_decisoes.head(10).drop(columns=['id'])
                    csv_dados  = df_revisao.to_csv(index=False, float_format='%.2f')
                    _prompt_diario = (
                        f"histórico das últimas decisões de investimento:\n{csv_dados}\n\n"
                        "analise os padrões e responda em 4 tópicos, letra minúscula:\n"
                        "1. padrão de sucesso: o que o investidor costuma fazer de certo nas decisões marcadas como acerto.\n"
                        "2. padrão de erro: o que costuma falhar nas decisões de erro.\n"
                        "3. viés comportamental: identifique o viés mais provável.\n"
                        "4. plano de ação: uma sugestão prática de melhoria."
                    )
                    chamar_ia(
                        prompt_usuario = _prompt_diario,
                        system         = SYSTEM_PORTFOLIO,
                        max_tokens     = 600,
                        temperatura    = 0.3,
                        stream         = True,
                    )
                except Exception as e:
                    st.error(f"falha ao conectar com o mentor de ia: {e}")

# ==========================================
# tab 5: imposto de renda
# ==========================================
with tab_ir:
    from utils.ir_calculator import calcular_ir_venda, gerar_resumo_mensal

    section_title("🧾 calculadora de imposto de renda")

    st.markdown(
        '<div style="font-family:Courier New; font-size:0.78rem; color:#555; '
        'margin-bottom:20px; line-height:1.6;">'
        '📋 <b>regras aplicadas:</b> ações BR (isenção R$ 20k/mês, 15% acima), '
        'FIIs (20% ganho de capital), ações EUA (15%), day trade (20%). '
        'compensação de prejuízos automática dentro da mesma categoria.</div>',
        unsafe_allow_html=True,
    )

    # ── calculadora rápida ────────────────────────────────────────────────────
    section_title("🧮 calculadora rápida de operação")

    with st.form("form_calc_ir"):
        col_a, col_b, col_c = st.columns(3)

        with col_a:
            ticker_ir = st.text_input(
                "ticker:", placeholder="WEGE3", key="ir_ticker"
            ).upper()
            tipo_ir = st.selectbox(
                "tipo de ativo:",
                options=['acao_br', 'fii', 'acao_us'],
                format_func=lambda x: {
                    'acao_br': '🇧🇷 Ação BR',
                    'fii':     '🏢 FII',
                    'acao_us': '🇺🇸 Ação EUA',
                }[x],
                key="ir_tipo",
            )
            day_trade_ir = st.checkbox("day trade?", key="ir_dt")

        with col_b:
            preco_compra_ir = st.number_input(
                "preço médio de compra (R$):",
                min_value=0.01, value=10.0,
                step=0.01, format="%.2f", key="ir_pc",
            )
            qtd_ir = st.number_input(
                "quantidade vendida:",
                min_value=1, value=100,
                step=1, key="ir_qtd",
            )
            custo_ir = st.number_input(
                "custos operacionais (R$):",
                min_value=0.0, value=0.0,
                step=0.01, format="%.2f",
                key="ir_custo",
                help="corretagem + emolumentos B3",
            )

        with col_c:
            preco_venda_ir = st.number_input(
                "preço de venda (R$):",
                min_value=0.01, value=12.0,
                step=0.01, format="%.2f", key="ir_pv",
            )
            outras_vendas_ir = st.number_input(
                "outras vendas no mês (R$):",
                min_value=0.0, value=0.0,
                step=100.0, format="%.2f",
                key="ir_outras",
                help="soma de outras vendas de ações no mês corrente",
            )
            prejuizo_ir = st.number_input(
                "prejuízo acumulado (R$):",
                min_value=0.0, value=0.0,
                step=100.0, format="%.2f",
                key="ir_prej",
                help="saldo negativo de meses anteriores (insira valor positivo)",
            )

        calcular_btn = st.form_submit_button(
            "🧮 calcular IR", type="primary", use_container_width=True,
        )

    if calcular_btn:
        resultado_ir = calcular_ir_venda(
            ticker           = ticker_ir or "TICKER",
            tipo_ativo       = tipo_ir,
            preco_compra     = preco_compra_ir,
            preco_venda      = preco_venda_ir,
            quantidade       = float(qtd_ir),
            custo_operacao   = custo_ir,
            day_trade        = day_trade_ir,
            total_vendas_mes = outras_vendas_ir,
            prejuizo_acum    = -abs(prejuizo_ir),
        )

        st.markdown("---")
        section_title("📊 resultado do cálculo")

        rc1, rc2, rc3, rc4 = st.columns(4)
        lucro  = resultado_ir['lucro_bruto']
        cor_l  = "bull" if lucro >= 0 else "bear"
        ir_dev = resultado_ir['ir_devido']

        with rc1:
            metric_card(
                "lucro/prejuízo bruto",
                f"R$ {lucro:,.2f}",
                f"receita: R$ {resultado_ir['receita_venda']:,.2f}",
                cor_delta=cor_l,
            )
        with rc2:
            if resultado_ir['prejuizo_comp'] > 0:
                metric_card(
                    "prejuízo compensado",
                    f"R$ {resultado_ir['prejuizo_comp']:,.2f}",
                    "deduzido do lucro tributável",
                    cor_delta="info",
                )
            else:
                metric_card(
                    "lucro tributável",
                    f"R$ {resultado_ir['lucro_tributavel']:,.2f}",
                    f"alíquota: {resultado_ir['aliquota'] * 100:.0f}%",
                    cor_delta=cor_l,
                )
        with rc3:
            metric_card(
                "ir a recolher (DARF)",
                f"R$ {ir_dev:,.2f}",
                "até último dia útil do mês seguinte",
                cor_delta="bear" if ir_dev > 0 else "bull",
            )
        with rc4:
            lucro_liq = lucro - ir_dev
            custo_base = preco_compra_ir * float(qtd_ir)
            retorno_pct = (lucro_liq / custo_base * 100) if custo_base > 0 else 0.0
            metric_card(
                "lucro líquido após IR",
                f"R$ {lucro_liq:,.2f}",
                f"retorno: {retorno_pct:+.1f}%",
                cor_delta="bull" if lucro_liq >= 0 else "bear",
            )

        # Regra aplicada + observações
        st.markdown(
            f'<div class="card" style="margin-top:12px; padding:14px; border-left:3px solid #00B0FF;">'
            f'<div style="font-family:Courier New; font-size:0.7rem; color:#555; '
            f'text-transform:uppercase; margin-bottom:6px;">regra aplicada</div>'
            f'<div style="font-family:Courier New; font-size:0.82rem; color:#E0E0E0;">'
            f'{resultado_ir["regra_aplicada"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        for obs in resultado_ir['observacoes']:
            st.markdown(
                f'<div style="font-family:Courier New; font-size:0.78rem; color:#888; '
                f'padding:5px 0; border-bottom:1px solid #1e1e1e;">{obs}</div>',
                unsafe_allow_html=True,
            )

        # Alerta DARF
        if resultado_ir['ir_devido'] >= 10.0:
            codigo_darf = "6015" if tipo_ir in ('acao_br', 'acao_us') else "3317"
            status_card(
                "⚡ lembrete: DARF",
                f"você tem R$ {resultado_ir['ir_devido']:,.2f} de IR a recolher. "
                f"emita o DARF pelo site da Receita Federal "
                f"(código {codigo_darf} para {'ações' if tipo_ir != 'fii' else 'FIIs'}) "
                f"até o último dia útil do próximo mês.",
                tipo="amber",
            )
        elif resultado_ir['isento']:
            status_card(
                "✅ operação isenta",
                "suas vendas neste mês estão abaixo do limite de R$ 20.000 — "
                "nenhum DARF precisa ser emitido para esta operação.",
                tipo="bull",
            )

    # ── guia de referência ────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("📚 guia rápido de alíquotas e regras (2024/2025)", expanded=False):
        regras = [
            ("🇧🇷 Ações BR — swing trade",
             "isenção total se vendas no mês ≤ R$ 20.000. "
             "acima desse limite: 15% sobre o lucro líquido. "
             "prejuízo pode ser compensado em meses futuros (mesma categoria)."),
            ("⚡ Ações BR — day trade",
             "20% sobre o lucro, sem isenção de R$ 20k. "
             "obrigatório retenção na fonte de 1% (IRRF) pela corretora."),
            ("🏢 FIIs",
             "20% sobre ganho de capital na venda. sem limite de isenção. "
             "proventos mensais distribuídos pelo fundo são isentos para pessoa física."),
            ("🇺🇸 Ações EUA / BDRs",
             "15% sobre lucro em reais. variação cambial entre a data de compra "
             "e venda também é tributável. sem isenção de R$ 20k."),
            ("📋 Compensação de prejuízos",
             "prejuízos em ações só compensam lucros de ações (não de FIIs). "
             "prejuízos em FIIs só compensam lucros de FIIs. "
             "sem prazo de validade — acumula até ser zerado."),
            ("📅 Prazo de pagamento",
             "DARF deve ser pago até o último dia útil do mês seguinte à operação. "
             "código DARF: 6015 (ações e day trade), 3317 (FIIs e fundos). "
             "valor mínimo de DARF: R$ 10,00 (abaixo disso, acumula para o próximo mês)."),
        ]
        for titulo, descricao in regras:
            st.markdown(
                f'<div style="margin-bottom:12px; padding:10px 14px; '
                f'background:#0d0d0d; border:1px solid #1e1e1e; border-radius:4px;">'
                f'<div style="font-family:Courier New; font-size:0.78rem; '
                f'color:#FF9900; font-weight:bold; margin-bottom:4px;">{titulo}</div>'
                f'<div style="font-family:Courier New; font-size:0.76rem; '
                f'color:#888; line-height:1.5;">{descricao}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

# ==========================================
# tab 6: chat ia
# ==========================================
with tab_chat:

    section_title("💬 chat com sua carteira — deepseek v4 pro")

    st.markdown(
        '<div style="font-family:Courier New; font-size:0.72rem; color:#333; '
        'margin-bottom:16px; line-height:1.5;">'
        'faça perguntas em linguagem natural sobre sua carteira. '
        'o modelo tem acesso completo às suas posições, health scores e métricas. '
        'não é recomendação de investimento.</div>',
        unsafe_allow_html=True,
    )

    # ── CARREGA DADOS SE NÃO ESTIVEREM NO SESSION_STATE ─────────────────

    # 1. Posições do portfólio
    # Usa o portfolio_id_ativo definido em tab_posicoes
    _portfolio_id_chat = portfolio_id_ativo
    _cache_key_pesos = f"pesos_ativos_cache_{_portfolio_id_chat}"
    pesos_chat = st.session_state.get(_cache_key_pesos, [])
    if not pesos_chat:
        pesos_chat = get_pesos(portfolio_id=_portfolio_id_chat)
        st.session_state[_cache_key_pesos] = pesos_chat

    # 2. Health scores
    health_chat = st.session_state.get("health_chat_cache", {})
    if not health_chat:
        health_chat = {h['ticker']: h for h in get_health_scores()}
        st.session_state["health_chat_cache"] = health_chat

    # 3. Cotações atuais (busca apenas tickers com posição)
    live_chat = st.session_state.get("live_data_cache", {})
    if not live_chat and pesos_chat:
        _tickers_chat = list(set([
            mapear_ticker_base(p['ticker'])
            for p in pesos_chat
            if float(p.get('quantidade') or 0) > 0
        ]))

        if _tickers_chat:
            try:
                with st.spinner("carregando dados da carteira..."):
                    _hist_chat = yf.download(
                        _tickers_chat,
                        period="2d",
                        auto_adjust=True,
                        progress=False,
                        multi_level_index=False,
                    )

                    if isinstance(_hist_chat.columns, pd.MultiIndex):
                        _hist_chat.columns = _hist_chat.columns.get_level_values(0)

                    _close = _hist_chat.get('Close', _hist_chat)

                    for _tc in _tickers_chat:
                        try:
                            if isinstance(_close, pd.DataFrame) and _tc in _close.columns:
                                _serie = _close[_tc].dropna()
                            elif isinstance(_close, pd.Series):
                                _serie = _close.dropna()
                            else:
                                continue

                            _pa = float(_serie.iloc[-1])
                            _pb = float(_serie.iloc[-2]) if len(_serie) >= 2 else _pa
                            _v1d = ((_pa / _pb) - 1) * 100 if _pb > 0 else 0.0
                            live_chat[_tc] = {'preco': _pa, 'var_1d': _v1d}
                        except Exception:
                            live_chat[_tc] = {'preco': 0.0, 'var_1d': 0.0}

                    st.session_state["live_data_cache"] = live_chat
            except Exception as _e:
                logger.warning(f"[chat] falha ao carregar cotações: {_e}")

    # 4. Métricas globais (opcionais — usa vazio se não tiver)
    metricas_chat = st.session_state.get("metricas_cache", {})

    # ── DEFINIÇÃO DA FUNÇÃO DE CONTEXTO ──────────────────────────────────

    def montar_contexto_carteira(
        posicoes: list,
        live_data_ctx: dict,
        health_data_ctx: dict,
        metricas_ctx: dict,
    ) -> str:
        """
        Serializa o estado da carteira em texto estruturado.
        Aceita tanto o formato enriquecido (vindo de pesos_ativos_cache)
        quanto o formato bruto do get_pesos(), enriquecendo on-the-fly com
        live_data_ctx e health_data_ctx.
        Gerado UMA VEZ e armazenado no session_state para cache hit.
        """
        linhas = ["estado atual da carteira do usuário:\n"]

        # Calcula totais para peso relativo
        _total_valor = 0.0
        _enriched = []
        for _p in posicoes:
            _qtd = float(_p.get('quantidade') or 0)
            _pm  = float(_p.get('preco_medio') or _p.get('preço médio') or 0)
            if _qtd <= 0:
                continue

            _tk     = _p.get('ticker', '')
            _tb     = mapear_ticker_base(_tk)
            # preco_atual: enriquecido ou vivo ou zero
            _pa     = float(_p.get('preco_atual') or
                            live_data_ctx.get(_tb, {}).get('preco') or
                            live_data_ctx.get(_tk, {}).get('preco') or 0)
            _valor  = _pa * _qtd if _pa > 0 else _pm * _qtd
            _total_valor += _valor

            _hs_raw = _p.get('health_score') or health_data_ctx.get(_tb, {}).get('score') or 50
            _pnl    = float(_p.get('pnl_pct') or
                            (((_pa / _pm) - 1) * 100 if _pm > 0 and _pa > 0 else 0))

            _enriched.append({
                'ticker':    _tk,
                'qtd':       _qtd,
                'pm':        _pm,
                'pa':        _pa,
                'valor':     _valor,
                'hs':        _hs_raw,
                'pnl':       _pnl,
            })

        if _enriched:
            linhas.append("posições:")
            for _e in _enriched:
                _peso_pct = (_e['valor'] / _total_valor * 100) if _total_valor > 0 else 0
                _hs_str   = f"{_e['hs']}/100" if isinstance(_e['hs'], (int, float)) else str(_e['hs'])
                _moeda    = "r$" if mapear_ticker_base(_e['ticker']).endswith('.SA') else "$"
                linhas.append(
                    f"- {_e['ticker']}: "
                    f"{_e['qtd']:.0f} cotas | "
                    f"preço {_moeda} {_e['pa']:,.2f} | "
                    f"pm {_moeda} {_e['pm']:,.2f} | "
                    f"valor {_moeda} {_e['valor']:,.0f} | "
                    f"peso {_peso_pct:.1f}% | "
                    f"health {_hs_str} | "
                    f"p&l {_e['pnl']:+.1f}%"
                )
        else:
            linhas.append("nenhuma posição encontrada.")

        if metricas_ctx:
            linhas.append(
                f"\nresumo da carteira:\n"
                f"- valor total (m2m): r$ {metricas_ctx.get('valor_total', 0):,.2f}\n"
                f"- custo total investido: r$ {metricas_ctx.get('custo_total', 0):,.2f}\n"
                f"- p&l total: {metricas_ctx.get('pnl_total_pct', 0):+.1f}%\n"
                f"- número de posições: {metricas_ctx.get('num_posicoes', 0)}"
            )
        elif _total_valor > 0:
            # fallback: calcula métricas da lista enriquecida
            _custo_total = sum(_e['pm'] * _e['qtd'] for _e in _enriched)
            _pnl_total   = ((_total_valor / _custo_total) - 1) * 100 if _custo_total > 0 else 0
            linhas.append(
                f"\nresumo da carteira:\n"
                f"- valor total (m2m): r$ {_total_valor:,.2f}\n"
                f"- custo total investido: r$ {_custo_total:,.2f}\n"
                f"- p&l total: {_pnl_total:+.1f}%\n"
                f"- número de posições: {len(_enriched)}"
            )

        macro = st.session_state.get("macro_context", {})
        if macro:
            linhas.append(
                f"\nambiente macro atual:\n"
                f"- selic: {macro.get('selic', 10.75):.2f}%\n"
                f"- vix: {macro.get('vix', 15.0):.1f}\n"
                f"- ambiente: {macro.get('label', 'neutro')}"
            )

        return "\n".join(linhas)

    # ── MONTA CONTEXTO (com invalidação se dados mudaram) ────────────────

    _ctx_key     = "chat_portfolio_contexto"
    _ctx_version = f"{_portfolio_id_chat}_{len(pesos_chat)}_{len(live_chat)}"

    if st.session_state.get("chat_ctx_version") != _ctx_version:
        st.session_state.pop(_ctx_key, None)
        st.session_state["chat_ctx_version"] = _ctx_version

    if _ctx_key not in st.session_state:
        st.session_state[_ctx_key] = montar_contexto_carteira(
            pesos_chat, live_chat, health_chat, metricas_chat
        )

    contexto_carteira = st.session_state[_ctx_key]

    # ── sugestões rápidas ─────────────────────────────────────────────────

    section_title("sugestões de perguntas")

    _sugestoes = [
        "qual meu ativo com pior health score?",
        "estou bem diversificado ou concentrado?",
        "meu p&l está bom para o ambiente macro atual?",
        "quais posições devo revisar primeiro?",
        "como o vix atual afeta minha carteira?",
        "qual meu ativo mais correlacionado com o ibov?",
        "qual posição tem maior risco de queda?",
        "devo rebalancear minha carteira agora?",
        "quais ativos estão próximos do stop loss?",
        "minha exposição a juros está adequada?",
    ]

    _cols_sug = st.columns(len(_sugestoes))
    for _i, _sug in enumerate(_sugestoes):
        with _cols_sug[_i]:
            _label = (_sug[:30] + "...") if len(_sug) > 30 else _sug
            if st.button(_label, key=f"chat_sug_{_i}",
                         use_container_width=True, help=_sug):
                st.session_state["chat_input_pendente"] = _sug

    # ── carrega user da sessão ────────────────────────────────────────────

    _user_id_chat = st.session_state.get('user_id', 0)

    # ── inicializa histórico (banco local + session_state) ────────────────

    _hist_key_db = f"chat_hist_loaded_{_portfolio_id_chat}"
    if "chat_portfolio_msgs" not in st.session_state:
        st.session_state["chat_portfolio_msgs"] = []
        # Carrega mensagens do banco local SQLite na primeira inicialização
        _hist_db = get_historico_chat(_user_id_chat, _portfolio_id_chat, limite=30)
        if _hist_db:
            st.session_state["chat_portfolio_msgs"] = [
                {'role': h['role'], 'content': h['conteudo']}
                for h in _hist_db
            ]
        st.session_state[_hist_key_db] = True

    # ── exibe histórico da conversa ───────────────────────────────────────

    st.markdown("---")

    for _msg in st.session_state["chat_portfolio_msgs"]:
        _role   = _msg["role"]
        _avatar = "👤" if _role == "user" else "⚡"
        with st.chat_message(_role, avatar=_avatar):
            st.markdown(
                f'<div style="font-family:Courier New; font-size:0.83rem; '
                f'color:#C0C0C0; line-height:1.6;">{_msg["content"]}</div>',
                unsafe_allow_html=True,
            )

    # ── input do usuário ──────────────────────────────────────────────────

    _input_default = st.session_state.pop("chat_input_pendente", "")

    _pergunta = st.chat_input(
        "pergunte sobre sua carteira...",
        key="chat_portfolio_input",
    ) or _input_default

    if _pergunta:
        # Adiciona ao histórico e exibe imediatamente
        st.session_state["chat_portfolio_msgs"].append(
            {"role": "user", "content": _pergunta}
        )
        salvar_mensagem_chat(_user_id_chat, _portfolio_id_chat, 'user', _pergunta)
        with st.chat_message("user", avatar="👤"):
            st.markdown(
                f'<div style="font-family:Courier New; font-size:0.83rem; '
                f'color:#E0E0E0;">{_pergunta}</div>',
                unsafe_allow_html=True,
            )

        # Monta o prompt: contexto (semi-estático) → histórico → pergunta atual
        # Ordem garante máximo cache hit no prefixo
        _msgs_ant = st.session_state["chat_portfolio_msgs"][:-1]
        _hist_txt = ""
        if _msgs_ant:
            _pares = []
            for _m in _msgs_ant[-6:]:   # últimas 3 trocas (6 mensagens)
                _pfx = "usuário" if _m["role"] == "user" else "analista"
                _pares.append(f"{_pfx}: {_m['content']}")
            _hist_txt = "\nhistórico recente:\n" + "\n".join(_pares) + "\n"

        _prompt_chat = (
            f"{contexto_carteira}"
            f"{_hist_txt}"
            f"\npergunta atual: {_pergunta}"
            f"\n\nresponda de forma direta e objetiva usando os dados da carteira acima. "
            f"letra minúscula."
        )

        _resposta = chamar_ia(
            prompt_usuario = _prompt_chat,
            system         = SYSTEM_PORTFOLIO,
            max_tokens     = 600,
            temperatura    = 0.3,
            stream         = True,
            thinking       = False,
        )

        # Salva resposta no histórico
        st.session_state["chat_portfolio_msgs"].append(
            {"role": "assistant", "content": _resposta}
        )
        salvar_mensagem_chat(_user_id_chat, _portfolio_id_chat, 'assistant', _resposta)

    # ── botão limpar ──────────────────────────────────────────────────────

    if st.session_state.get("chat_portfolio_msgs"):
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🗑️ limpar conversa", key="btn_limpar_chat"):
            limpar_historico_chat(_user_id_chat, _portfolio_id_chat)
            st.session_state["chat_portfolio_msgs"] = []
            st.session_state.pop(_ctx_key, None)
            st.session_state.pop(_hist_key_db, None)
            st.rerun()