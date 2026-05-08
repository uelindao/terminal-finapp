import streamlit as st
import requests
import json
import datetime
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import sqlite3

# Importações do projeto
from utils.style import aplicar_tema
from utils.tickers import XSTOCKS_LABELS, XSTOCKS_TODOS

# --- Configuração da Página ---
st.set_page_config(page_title="Portfólio Solana", layout="wide", initial_sidebar_state="collapsed")

# --- Injeta o CSS Centralizado ---
aplicar_tema()

# ==========================================
# BANCO DE DADOS LOCAL (Salvar Carteira e Mints)
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
# DIAGNÓSTICO DE CARTEIRA (Briefing 1)
# ==========================================
def diagnosticar_carteira(tokens: list[dict]) -> dict:
    """Analisa o perfil da carteira e retorna um diagnóstico."""
    total = len(tokens)
    gaming_keywords = ['ship', 'atlas', 'polis', 'part', 'nft', 'hero', 'game', 'play']
    defi_keywords = ['sol', 'jup', 'lp', 'usdc', 'usdt', 'swap', 'perp', 'ray', 'orca']
    rwa_keywords = ['stock', 'share', 'equity', 'backed', 'tokenized', 'rwa', 'dinari', 'ondo']

    contagem = {'gaming': 0, 'defi': 0, 'rwa': 0, 'outros': 0}

    for token in tokens:
        nome = (token.get('name', '') + ' ' + token.get('symbol', '')).lower()
        if any(k in nome for k in gaming_keywords):
            contagem['gaming'] += 1
        elif any(k in nome for k in defi_keywords):
            contagem['defi'] += 1
        elif any(k in nome for k in rwa_keywords):
            contagem['rwa'] += 1
        else:
            contagem['outros'] += 1

    if total == 0:
        perfil = 'vazia'
    else:
        perfil = max(contagem, key=contagem.get)

    return {
        'perfil_dominante': perfil,
        'contagens': contagem,
        'total': total,
        'aviso': perfil in ('gaming', 'defi')
    }

# ==========================================
# FUNÇÕES DE INTEGRAÇÃO API
# ==========================================
@st.cache_data(ttl=86400, show_spinner=False)
def get_jupiter_stock_tokens() -> dict:
    """Baixa a lista de tokens do Jupiter e filtra apenas os que parecem ser ações."""
    try:
        resp = requests.get(
            "https://token.jup.ag/all",
            timeout=30,
            headers={"User-Agent": "FinTerminal/1.0"}
        )
        if resp.status_code == 200:
            todos_tokens = resp.json()
            mapeamento = {}
            rwa_keywords = ['STOCK', 'SHARE', 'BACKED', 'TOKENIZED', 'EQUITY', 'TOKEN']
            
            for token in todos_tokens:
                simbolo = token.get('symbol', '').upper().strip()
                mint = token.get('address', '')
                nome = token.get('name', '').upper()

                if not mint or not simbolo:
                    continue

                if simbolo in XSTOCKS_TODOS:
                    mapeamento[mint] = simbolo
                    continue

                if simbolo.startswith('B') and simbolo[1:] in XSTOCKS_TODOS:
                    mapeamento[mint] = simbolo[1:]
                    continue

                if simbolo.startswith(('X', 'D', 'W')) and simbolo[1:] in XSTOCKS_TODOS:
                    mapeamento[mint] = simbolo[1:]
                    continue

                for ticker in XSTOCKS_TODOS:
                    if ticker in nome and any(kw in nome for kw in rwa_keywords):
                        mapeamento[mint] = ticker
                        break
            return mapeamento
    except Exception as e:
        pass
    return {}

def get_token_metadata_helius(mints: list[str]) -> dict:
    """Busca nomes e símbolos via Helius DAS API."""
    api_key = st.secrets.get("HELIUS_API_KEY", "")
    if not api_key: return {}
    url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"
    headers = {"Content-Type": "application/json"}
    metadata_dict = {}
    
    for i in range(0, len(mints), 100):
        chunk = mints[i:i + 100]
        payload = {"jsonrpc": "2.0", "id": "my-id", "method": "getAssetBatch", "params": {"ids": chunk}}
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
        except: pass
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
                    compras.append({'data': data, 'quantidade': quantidade, 'valor_usd_estimado': valor_usd})

    if not compras: return {'preco_medio': None, 'quantidade': 0, 'primeira_compra': None}
    qtd_total = sum(c['quantidade'] for c in compras)
    valor_total = sum(c['valor_usd_estimado'] for c in compras)
    return {
        'preco_medio': valor_total / qtd_total if qtd_total > 0 else None,
        'quantidade': qtd_total,
        'primeira_compra': min(c['data'] for c in compras)
    }

def mapear_token_para_ticker(mint: str, simbolo: str, nome: str) -> str | None:
    # 1. Tenta encontrar no banco de dados customizado pelo usuário
    try:
        conn = sqlite3.connect('data/finapp.db', check_same_thread=False)
        row = conn.execute("SELECT ticker FROM custom_mints WHERE mint = ?", (mint,)).fetchone()
        conn.close()
        if row: return row[0]
    except: pass

    # 2. Tenta o mapa dinâmico da Jupiter
    jupiter_map = get_jupiter_stock_tokens()
    if mint in jupiter_map:
        return jupiter_map[mint]

    # 3. Fallback Hardcoded
    XSTOCK_MINTS_FALLBACK = {"3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh": "WBTC"}
    if mint in XSTOCK_MINTS_FALLBACK:
        return XSTOCK_MINTS_FALLBACK[mint]

    # 4. Match direto por símbolo
    simbolo_limpo = str(simbolo).upper().strip()
    if simbolo_limpo in XSTOCKS_TODOS:
        return simbolo_limpo
    if len(simbolo_limpo) > 1 and simbolo_limpo[0] in ['B', 'D', 'X', 'W']:
        ticker_base = simbolo_limpo[1:]
        if ticker_base in XSTOCKS_TODOS:
            return ticker_base

    return None

# ==========================================
# INTERFACE DA PÁGINA
# ==========================================
st.markdown("### ⛓️ PORTFÓLIO ON-CHAIN — XSTOCKS / SOLANA")
st.write("Conecte sua carteira Solana para visualizar seus ativos tokenizados.")
st.info("🔒 Apenas o endereço PÚBLICO é necessário. Nunca compartilhe sua seed phrase ou chave privada.")

saved_wallet = get_saved_wallet()

col1, col2 = st.columns([5, 3])
with col1:
    wallet = st.text_input("ENDEREÇO PÚBLICO DA CARTEIRA SOLANA:", value=saved_wallet, placeholder="Ex: 7xKX...abc123").strip()
with col2:
    st.markdown("<br>", unsafe_allow_html=True)
    btn_conectar = st.button("🔗 CONECTAR CARTEIRA", type="primary", use_container_width=True)

if not st.secrets.get("HELIUS_API_KEY"):
    st.warning("⚠️ HELIUS_API_KEY não configurada no secrets.toml. Obtenha sua chave gratuita em dashboard.helius.xyz")
    st.stop()

if btn_conectar and wallet:
    if wallet != saved_wallet:
        save_wallet_address(wallet)
        
    with st.spinner("Lendo blockchain Solana..."):
        tokens = get_token_accounts(wallet)

    if not tokens:
        st.warning("Nenhum token encontrado ou a carteira indicada é inválida.")
        st.stop()

    mints_to_fetch = [t.get('mint') for t in tokens if float(t.get('amount', 0)) > 0]
    
    with st.spinner("Construindo metadados e diagnosticando perfil da carteira..."):
        metadata_dict = get_token_metadata_helius(mints_to_fetch)
        
        # Constrói lista rica para diagnóstico
        tokens_com_metadata = []
        for t in tokens:
            mint = t.get('mint')
            if mint in mints_to_fetch:
                meta = metadata_dict.get(mint, {})
                tokens_com_metadata.append({
                    'mint': mint,
                    'amount': t.get('amount'),
                    'symbol': meta.get('symbol', '?'),
                    'name': meta.get('name', 'Token Desconhecido')
                })
                
        diagnostico = diagnosticar_carteira(tokens_com_metadata)

    if diagnostico['aviso']:
        st.warning(f"""
        ⚠️ Esta carteira parece ser predominantemente de 
        **{'Gaming' if diagnostico['perfil_dominante'] == 'gaming' else 'DeFi'}** ({diagnostico['contagens'][diagnostico['perfil_dominante']]} tokens desse ecossistema identificados).

        Seus investimentos em XStocks estão possivelmente em outra carteira Phantom.
        Verifique qual endereço foi utilizado para comprar as ações tokenizadas.
        """)

    xstocks_encontrados = []
    tokens_nao_mapeados = []

    for t in tokens_com_metadata:
        ticker_yf = mapear_token_para_ticker(t['mint'], t['symbol'], t['name'])
        
        if ticker_yf:
            xstocks_encontrados.append({
                'ticker': ticker_yf,
                'mint': t['mint'],
                'quantidade_on_chain': float(t['amount']),
                'simbolo_token': t['symbol'],
                'nome_token': t['name'],
            })
        else:
            tokens_nao_mapeados.append(t)

    # ==========================================
    # SEÇÃO: HOLDINGS MAPEADOS
    # ==========================================
    st.markdown("---")
    st.markdown(f"#### 🎯 XStocks Identificados ({len(xstocks_encontrados)} ativos)")

    if xstocks_encontrados:
        with st.spinner("Buscando cotações atuais na Bolsa..."):
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

            st.caption("* P&L marcado como N/D: O cálculo de custo médio requer parsing avançado de swaps Jupiter. Insira manualmente na página 'Portfolio Analytics'.")

            total_valor = df_port['Valor Atual $'].sum()
            total_pnl = df_port['P&L $'].dropna().sum()
            st.metric("VALOR TOTAL ON-CHAIN", f"$ {total_valor:,.2f}", delta=f"P&L: $ {total_pnl:+,.2f}" if total_pnl else None)

            fig_pie = go.Figure(go.Pie(labels=df_port['Ticker'], values=df_port['Valor Atual $'], hole=0.4, textinfo='label+percent'))
            fig_pie.update_layout(paper_bgcolor="#010101", plot_bgcolor="#010101", font=dict(family="Courier New", color="#E0E0E0"), height=350, margin=dict(l=0,r=0,t=20,b=0))
            st.plotly_chart(fig_pie, use_container_width=True)

    # ==========================================
    # SEÇÃO: TOKENS NÃO MAPEADOS
    # ==========================================
    if tokens_nao_mapeados:
        with st.expander(f"❓ Tokens não reconhecidos ({len(tokens_nao_mapeados)})", expanded=False):
            st.write("Estes tokens não foram identificados como XStocks conhecidos:")
            for tok in tokens_nao_mapeados[:15]:
                st.text(f"{tok.get('symbol','?')} | {tok.get('mint','')[:20]}... | Qtd: {float(tok.get('amount',0)):.4f}")
            st.caption("Se algum destes for um XStock que você opera, copie o endereço Mint e registre-o manualmente na secção abaixo.")

# ==========================================
# SEÇÃO: REGISTRO MANUAL DE TOKENS
# ==========================================
st.markdown("---")
with st.expander("⚙️ REGISTRO MANUAL DE TOKENS", expanded=False):
    st.write("Se os seus XStocks aparecem na lista de 'tokens não reconhecidos', copie o endereço Mint e registre-o aqui para que o sistema os identifique automaticamente nas próximas consultas.")

    col_m1, col_m2, col_m3 = st.columns([3, 2, 1])
    with col_m1:
        mint_manual = st.text_input("Endereço Mint do token:", placeholder="Ex: EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
    with col_m2:
        ticker_manual = st.selectbox("Ticker correspondente:", [""] + sorted(XSTOCKS_TODOS))
    with col_m3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("SALVAR", use_container_width=True) and mint_manual and ticker_manual:
            conn = sqlite3.connect('data/finapp.db')
            conn.execute("REPLACE INTO custom_mints (mint, ticker) VALUES (?, ?)", (mint_manual.strip(), ticker_manual))
            conn.commit()
            conn.close()
            st.success(f"✅ {mint_manual[:12]}... mapeado para {ticker_manual}")
            st.rerun()

    try:
        conn = sqlite3.connect('data/finapp.db')
        custom = conn.execute("SELECT mint, ticker FROM custom_mints").fetchall()
        conn.close()
        if custom:
            st.markdown("**Mapeamentos registrados na sua base de dados local:**")
            for mint_c, ticker_c in custom:
                c1, c2, c3 = st.columns([4, 2, 1])
                c1.text(f"{mint_c[:20]}...")
                c2.text(ticker_c)
                if c3.button("✕", key=f"del_{mint_c}"):
                    conn = sqlite3.connect('data/finapp.db')
                    conn.execute("DELETE FROM custom_mints WHERE mint = ?", (mint_c,))
                    conn.commit()
                    conn.close()
                    st.rerun()
    except:
        pass