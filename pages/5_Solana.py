import streamlit as st
import requests
import json
import datetime
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import sqlite3

from utils.auth import check_password

import streamlit as st
# (mantenha os outros imports do python e das suas pastas aqui...)

# 1. substitua a importação antiga por esta:
from utils.auth import require_auth, render_user_badge
from utils.style import aplicar_tema

# 2. o set_page_config TEM de vir antes do require_auth
st.set_page_config(page_title="terminal finapp", layout="wide")

# 3. nova barreira de segurança multi-usuário
if not require_auth():
    st.stop()

# 4. renderiza o nome do utilizador no menu lateral e aplica o tema
render_user_badge()
aplicar_tema()
# (continue com o resto do código: inject_keyboard_shortcuts(), page_header, etc...)

# Importações do projeto
from utils.style import aplicar_tema
from utils.tickers import XSTOCKS_LABELS, XSTOCKS_TODOS

# --- Configuração da Página ---
st.set_page_config(page_title="Portfólio Solana", layout="wide", initial_sidebar_state="collapsed")

# --- Injeta o CSS Centralizado ---
aplicar_tema()

# ==========================================
# BANCO DE DADOS LOCAL (Salvar Carteira)
# ==========================================
def init_solana_db():
    conn = sqlite3.connect('data/finapp.db', check_same_thread=False)
    conn.execute("CREATE TABLE IF NOT EXISTS config_solana (id INTEGER PRIMARY KEY, wallet TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS custom_mints (mint TEXT PRIMARY KEY, ticker TEXT)")
    conn.commit()
    conn.close()

def save_wallet_address(wallet_address):
    conn = sqlite3.connect('data/finapp.db', check_same_thread=False)
    conn.execute("REPLACE INTO config_solana (id, wallet) VALUES (1, ?)", (wallet_address,))
    conn.commit()
    conn.close()

def get_saved_wallet():
    conn = sqlite3.connect('data/finapp.db', check_same_thread=False)
    try:
        row = conn.execute("SELECT wallet FROM config_solana WHERE id = 1").fetchone()
        return row[0] if row else ""
    except:
        return ""
    finally:
        conn.close()

init_solana_db()

# ==========================================
# MAPEAMENTO HARDCODED (Backup)
# ==========================================
XSTOCK_MINTS = {
    "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh": "WBTC",
}

# ==========================================
# FUNÇÕES DE INTEGRAÇÃO (HELIUS RPC + DAS API + JUPITER)
# ==========================================
@st.cache_data(ttl=86400, show_spinner=False)
def get_jupiter_rwa_map() -> dict:
    """
    Baixa a lista de tokens do Jupiter e filtra apenas os que
    parecem ser ações tokenizadas (RWA).
    Retorna: {mint_address: ticker_yfinance}
    Cache de 24h para não sobrecarregar a API.
    """
    from utils.tickers import XSTOCKS_TODOS

    try:
        resp = requests.get(
            "https://token.jup.ag/all",
            timeout=30,
            headers={"User-Agent": "FinTerminal/1.0"}
        )
        resp.raise_for_status()
        todos_tokens = resp.json()
    except Exception:
        return {}  # Falha silenciosa — não quebra a página

    mapeamento = {}
    prefixos_rwa = ['B', 'D', 'X', 'T', 'W', 'O', 'S']

    for token in todos_tokens:
        simbolo = token.get('symbol', '').upper().strip()
        mint    = token.get('address', '')
        nome    = token.get('name', '').upper()

        if not mint or not simbolo or simbolo == '?':
            continue

        # Match direto
        if simbolo in XSTOCKS_TODOS:
            mapeamento[mint] = simbolo
            continue

        # Match com prefixo RWA
        if len(simbolo) > 1 and simbolo[0] in prefixos_rwa:
            base = simbolo[1:]
            if base in XSTOCKS_TODOS:
                mapeamento[mint] = base
                continue

        # Match com separador
        for sep in ['.', '-', '_']:
            if sep in simbolo:
                for parte in simbolo.split(sep):
                    if parte in XSTOCKS_TODOS:
                        mapeamento[mint] = parte
                        break

    return mapeamento

def get_token_metadata_helius(mints: list[str]) -> dict:
    """Busca nomes e símbolos dos tokens diretamente via Helius DAS API."""
    api_key = st.secrets.get("HELIUS_API_KEY", "")
    if not api_key:
        return {}

    url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"
    headers = {"Content-Type": "application/json"}
    metadata_dict = {}
    
    chunk_size = 100
    for i in range(0, len(mints), chunk_size):
        chunk = mints[i:i + chunk_size]
        payload = {
            "jsonrpc": "2.0",
            "id": "my-id",
            "method": "getAssetBatch",
            "params": {"ids": chunk}
        }
        
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=20)
            if resp.status_code == 200:
                result = resp.json().get('result', [])
                for asset in result:
                    if asset and isinstance(asset, dict):
                        mint_id = asset.get('id')
                        content = asset.get('content', {}).get('metadata', {})
                        token_info = asset.get('token_info', {})
                        
                        symbol = content.get('symbol') or token_info.get('symbol') or '?'
                        name = content.get('name') or token_info.get('name') or 'Token Desconhecido'
                        
                        metadata_dict[mint_id] = {'symbol': symbol, 'name': name}
        except:
            pass
            
    return metadata_dict

def get_token_accounts(wallet_address: str) -> list[dict]:
    api_key = st.secrets.get("HELIUS_API_KEY", "")
    url = f"https://api.helius.xyz/v0/addresses/{wallet_address}/balances?api-key={api_key}"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json().get('tokens', [])
    except Exception as e:
        st.error(f"Erro ao comunicar com a Helius API: {e}")
        return []

def get_transaction_history(wallet_address: str, mint: str, limit: int = 50) -> list[dict]:
    api_key = st.secrets.get("HELIUS_API_KEY", "")
    url = f"https://api.helius.xyz/v0/addresses/{wallet_address}/transactions?api-key={api_key}&limit={limit}"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        txs = resp.json()
        return [tx for tx in txs if any(t.get('mint') == mint for t in tx.get('tokenTransfers', []))]
    except:
        return []

def mapear_token_para_ticker(mint: str, simbolo: str, nome: str) -> str | None:
    """Tenta mapear um token Solana para um ticker yfinance conhecido."""

    # 0. Consulta Jupiter Token List (autodescoberta automática — maior prioridade)
    jupiter_map = get_jupiter_rwa_map()
    if mint in jupiter_map:
        return jupiter_map[mint]

    # 1. XSTOCK_MINTS hardcoded (fallback manual)
    if mint in XSTOCK_MINTS:
        return XSTOCK_MINTS[mint]

    simbolo_limpo = str(simbolo).upper().strip()

    if simbolo_limpo == '?' or not simbolo_limpo:
        return None

    # 1. Match Direto EXATO
    if simbolo_limpo in XSTOCKS_TODOS:
        return simbolo_limpo

    # 2. Match por prefixos de protocolos RWA conhecidos
    RWA_PREFIXES = ['B', 'D', 'X', 'T', 'W', 'O', 'S', 'R']
    if len(simbolo_limpo) > 1 and simbolo_limpo[0] in RWA_PREFIXES:
        ticker_base = simbolo_limpo[1:]
        if ticker_base in XSTOCKS_TODOS:
            return ticker_base

    # 3. Match com sufixo (ex: AAPL.b, TSLA.x, NVDA-b)
    for sep in ['.', '-', '_']:
        if sep in simbolo_limpo:
            partes = simbolo_limpo.split(sep)
            for parte in partes:
                if parte in XSTOCKS_TODOS:
                    return parte

    # 4. Consulta custom_mints do banco (mapeamentos manuais do usuário)
    try:
        conn = sqlite3.connect('data/finapp.db')
        row = conn.execute(
            "SELECT ticker FROM custom_mints WHERE mint = ?",
            (mint,)
        ).fetchone()
        conn.close()
        if row:
            return row[0]
    except:
        pass

    return None

def calcular_custo_medio_onchain(txs: list[dict], mint: str) -> dict:
    compras = []
    for tx in txs:
        timestamp = tx.get('timestamp', 0)
        data = datetime.datetime.fromtimestamp(timestamp)
        for transfer in tx.get('tokenTransfers', []):
            if transfer.get('mint') == mint:
                quantidade = transfer.get('tokenAmount', 0)
                valor_usd = 0
                for native in tx.get('nativeTransfers', []):
                    valor_usd += native.get('amount', 0) / 1e9 * 150 
                
                if quantidade > 0:
                    compras.append({
                        'data': data,
                        'quantidade': quantidade,
                        'valor_usd_estimado': valor_usd
                    })

    if not compras: return {'preco_medio': None, 'quantidade': 0, 'primeira_compra': None}
    qtd_total = sum(c['quantidade'] for c in compras)
    valor_total = sum(c['valor_usd_estimado'] for c in compras)
    return {
        'preco_medio': valor_total / qtd_total if qtd_total > 0 else None,
        'quantidade': qtd_total,
        'primeira_compra': min(c['data'] for c in compras)
    }

# ==========================================
# INTERFACE DA PÁGINA
# ==========================================
st.markdown("### ⛓️ PORTFÓLIO ON-CHAIN — XSTOCKS / SOLANA")
st.write("Conecte sua carteira Solana para visualizar seus ativos tokenizados.")
st.info("🔒 Apenas o endereço PÚBLICO é necessário. Nunca compartilhe sua seed phrase ou chave privada.")

saved_wallet = get_saved_wallet()

col1, col2 = st.columns([5, 3])
with col1:
    wallet = st.text_input(
        "ENDEREÇO PÚBLICO DA CARTEIRA SOLANA:",
        value=saved_wallet,
        placeholder="Ex: 7xKX...abc123"
    ).strip()
with col2:
    st.markdown("<br>", unsafe_allow_html=True)
    btn_conectar = st.button("🔗 CONECTAR CARTEIRA", type="primary", use_container_width=True)

if not st.secrets.get("HELIUS_API_KEY"):
    st.warning("⚠️ HELIUS_API_KEY não configurada no ficheiro secrets.toml.")
    st.stop()

if btn_conectar and wallet:
    
    if wallet != saved_wallet:
        save_wallet_address(wallet)
        
    with st.spinner("Lendo a blockchain Solana..."):
        tokens = get_token_accounts(wallet)

    if not tokens:
        st.warning("Nenhum token encontrado ou a carteira indicada é inválida.")
        st.stop()

    mints_to_fetch = [t.get('mint') for t in tokens if float(t.get('amount', 0)) > 0]
    
    with st.spinner("Buscando nomes e símbolos dos ativos na Helius..."):
        metadata_dict = get_token_metadata_helius(mints_to_fetch)

    with st.spinner("Consultando Jupiter Token List para identificar ativos RWA..."):
        jupiter_map = get_jupiter_rwa_map()
        n_rwa_conhecidos = len(jupiter_map)

    st.caption(
        f"ℹ️ Base de dados RWA: {n_rwa_conhecidos} tokens identificados "
        f"no ecossistema Solana via Jupiter."
    )

    xstocks_encontrados = []
    tokens_nao_mapeados = []

    for token in tokens:
        amount = float(token.get('amount', 0))
        if amount <= 0: continue

        mint = token.get('mint')
        
        meta = metadata_dict.get(mint, {})
        simbolo = meta.get('symbol', '?')
        nome = meta.get('name', 'Token Desconhecido')

        ticker_yf = mapear_token_para_ticker(mint, simbolo, nome)
        
        if ticker_yf:
            xstocks_encontrados.append({
                'ticker': ticker_yf,
                'mint': mint,
                'quantidade_on_chain': amount,
                'simbolo_token': simbolo,
                'nome_token': nome,
            })
        else:
            tokens_nao_mapeados.append({
                'mint': mint,
                'amount': amount,
                'symbol': simbolo,
                'name': nome
            })

    # ==========================================
    # SEÇÃO: HOLDINGS MAPEADOS
    # ==========================================
    st.markdown("---")
    st.markdown(f"#### 🎯 XStocks Identificados ({len(xstocks_encontrados)} ativos)")

    if xstocks_encontrados:
        with st.spinner("Buscando cotações atuais na Bolsa de NY (yfinance)..."):
            rows = []
            for xs in xstocks_encontrados:
                t = xs['ticker']
                try:
                    fi = yf.Ticker(t).fast_info
                    preco_atual = fi.last_price
                    preco_abertura = fi.open or preco_atual
                    var_1d = ((preco_atual/preco_abertura)-1)*100

                    txs = get_transaction_history(wallet, xs['mint'], limit=20)
                    custo_info = calcular_custo_medio_onchain(txs, xs['mint'])

                    qtd = xs['quantidade_on_chain']
                    pm  = custo_info['preco_medio']
                    valor_atual = preco_atual * qtd
                    custo_total = pm * qtd if pm else None
                    pnl = valor_atual - custo_total if custo_total else None
                    pnl_pct = (pnl/custo_total*100) if custo_total else None

                    rows.append({
                        'Ticker': t,
                        'Token Real': xs['simbolo_token'],
                        'Qtd On-Chain': qtd,
                        'Preço Atual $': preco_atual,
                        'Var 1D %': var_1d,
                        'Valor Atual $': valor_atual,
                        'Preço Médio $': pm,
                        'Custo Total $': custo_total,
                        'P&L $': pnl,
                        'P&L %': pnl_pct,
                        'Primeira Compra': custo_info.get('primeira_compra'),
                    })
                except: pass

        df_port = pd.DataFrame(rows)

        if not df_port.empty:
            def colorir_pnl(val):
                if pd.isna(val) or val == 0: return ''
                return 'color: #00FF00' if val > 0 else 'color: #FF0000'

            st.dataframe(
                df_port.style
                    .applymap(colorir_pnl, subset=['P&L $','P&L %','Var 1D %'])
                    .format({
                        'Preço Atual $': '${:.2f}', 'Valor Atual $': '${:.2f}',
                        'Preço Médio $': lambda x: f'${x:.2f}' if pd.notna(x) else 'N/D*',
                        'Custo Total $': lambda x: f'${x:.2f}' if pd.notna(x) else 'N/D*',
                        'P&L $': lambda x: f'${x:+.2f}' if pd.notna(x) else 'N/D*',
                        'P&L %': lambda x: f'{x:+.2f}%' if pd.notna(x) else 'N/D*',
                        'Var 1D %': '{:+.2f}%', 'Qtd On-Chain': '{:.4f}',
                        'Primeira Compra': lambda x: x.strftime('%Y-%m-%d') if pd.notna(x) else 'N/D'
                    }, na_rep='—'), use_container_width=True
            )

            st.caption("* P&L marcado como N/D: O cálculo exato do custo médio requer um *parsing* avançado de swaps em DEXs. Insira manualmente na página 'Portfolio Analytics'.")

            total_valor = df_port['Valor Atual $'].sum()
            total_pnl = df_port['P&L $'].dropna().sum()
            st.metric("VALOR TOTAL ON-CHAIN (RWA)", f"$ {total_valor:,.2f}", delta=f"P&L Rastreável: $ {total_pnl:+,.2f}" if total_pnl else None)

            fig_pie = go.Figure(go.Pie(labels=df_port['Ticker'], values=df_port['Valor Atual $'], hole=0.4, textinfo='label+percent'))
            fig_pie.update_layout(paper_bgcolor="#010101", plot_bgcolor="#010101", font=dict(family="Courier New", color="#E0E0E0"), height=350, margin=dict(l=0,r=0,t=20,b=0))
            st.plotly_chart(fig_pie, use_container_width=True)

    # ==========================================
    # SEÇÃO: TOKENS NÃO MAPEADOS
    # ==========================================
    if tokens_nao_mapeados:
        with st.expander(
            f"❓ Outros tokens na carteira ({len(tokens_nao_mapeados)}) — "
            f"clique para ver todos e verificar se algum é XStock",
            expanded=True  
        ):
            st.info(
                "Todos os tokens da carteira que não foram automaticamente "
                "identificados como XStocks estão listados abaixo. "
                "Se algum deles for uma ação tokenizada, copie o Mint e "
                "registre na seção de mapeamento manual abaixo."
            )

            # Campo de busca para filtrar tokens na lista
            filtro = st.text_input(
                "🔍 Buscar token pelo símbolo ou nome:",
                placeholder="Ex: AAPL, Tesla, backed...",
                key="filtro_tokens_nao_mapeados"
            ).upper()

            # Aplicar filtro se preenchido
            lista_exibir = tokens_nao_mapeados
            if filtro:
                lista_exibir = [
                    tok for tok in tokens_nao_mapeados
                    if filtro in tok.get('symbol', '').upper()
                    or filtro in tok.get('name', '').upper()
                ]
                st.caption(f"Mostrando {len(lista_exibir)} de {len(tokens_nao_mapeados)} tokens.")

            # Exibir TODOS os tokens (sem limite [:20])
            for tok in lista_exibir:
                sym  = tok.get('symbol', '?')
                nome = tok.get('name', 'Token Desconhecido')
                qtd  = tok.get('amount', 0)
                mint = tok.get('mint', '')

                col_info, col_copy = st.columns([6, 2])
                with col_info:
                    st.markdown(
                        f'<div style="font-family:Courier New; font-size:0.82rem; '
                        f'padding:4px 0; border-bottom:1px solid #1a1a1a;">'
                        f'<span style="color:#FF9900; font-weight:bold;">{sym}</span> '
                        f'<span style="color:#888;">({nome})</span> | '
                        f'Qtd: <span style="color:#FFF;">{qtd:.4f}</span> | '
                        f'Mint: <span style="color:#555;">{mint[:20]}...</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                with col_copy:
                    # Botão para copiar o mint address completo
                    if st.button("📋 Mint", key=f"cp_{mint[:10]}",
                                 help=f"Mint completo: {mint}"):
                        st.code(mint, language="text")

            # Seção de mapeamento manual (logo abaixo da lista)
            st.markdown("---")
            st.markdown("**📝 Registrar mapeamento manual:**")
            st.caption(
                "Se você identificou um XStock na lista acima, clique em '📋 Mint' "
                "para ver o endereço completo, depois registre aqui:"
            )

            col_m1, col_m2, col_m3 = st.columns([4, 2, 1])
            with col_m1:
                mint_manual = st.text_input(
                    "Mint Address completo:",
                    placeholder="Cole o endereço completo aqui",
                    key="mint_manual_input"
                ).strip()
            with col_m2:
                from utils.tickers import XSTOCKS_TODOS
                ticker_manual = st.selectbox(
                    "Ticker correspondente:",
                    [""] + sorted(XSTOCKS_TODOS),
                    key="ticker_manual_sel"
                )
            with col_m3:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("SALVAR", key="btn_salvar_mint",
                             use_container_width=True, type="primary"):
                    if mint_manual and ticker_manual:
                        conn = sqlite3.connect('data/finapp.db')
                        conn.execute(
                            "CREATE TABLE IF NOT EXISTS custom_mints "
                            "(mint TEXT PRIMARY KEY, ticker TEXT)"
                        )
                        conn.execute(
                            "REPLACE INTO custom_mints (mint, ticker) VALUES (?, ?)",
                            (mint_manual, ticker_manual)
                        )
                        conn.commit()
                        conn.close()
                        st.success(
                            f"✅ Token mapeado: ...{mint_manual[-8:]} → {ticker_manual}. "
                            f"Clique em 'Conectar Carteira' novamente para reclassificar."
                        )
                    else:
                        st.warning("Preencha o Mint Address e selecione o ticker.")

            # Exibir mapeamentos já salvos
            try:
                conn = sqlite3.connect('data/finapp.db')
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS custom_mints "
                    "(mint TEXT PRIMARY KEY, ticker TEXT)"
                )
                custom = conn.execute(
                    "SELECT mint, ticker FROM custom_mints"
                ).fetchall()
                conn.close()

                if custom:
                    st.markdown("**Mapeamentos registrados:**")
                    for mint_c, ticker_c in custom:
                        c1, c2, c3 = st.columns([5, 2, 1])
                        c1.code(f"{mint_c[:25]}...", language="text")
                        c2.markdown(
                            f'<span style="color:#FF9900; font-family:Courier New;">'
                            f'{ticker_c}</span>',
                            unsafe_allow_html=True
                        )
                        if c3.button("✕", key=f"del_{mint_c[:8]}"):
                            conn = sqlite3.connect('data/finapp.db')
                            conn.execute(
                                "DELETE FROM custom_mints WHERE mint = ?", (mint_c,)
                            )
                            conn.commit()
                            conn.close()
                            st.rerun()
            except:
                pass