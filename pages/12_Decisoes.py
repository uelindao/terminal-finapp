import streamlit as st
import yfinance as yf
import pandas as pd
import datetime
from google import genai

from utils.auth import check_password

if not check_password():
    st.stop()

from utils.style import aplicar_tema
from utils.tickers import get_opcoes_selectbox, ticker_from_label
from database.db import registrar_decisao, listar_decisoes, atualizar_resultado

# --- Configuração da Página ---
st.set_page_config(page_title="Diário de Decisões", layout="wide", initial_sidebar_state="collapsed")
aplicar_tema()

st.markdown("### 📝 DIÁRIO DE DECISÕES (TRADING JOURNAL)")
st.write("Registe as suas teses de investimento e audite a sua taxa de acerto ao longo do tempo.")

# ==========================================
# SEÇÃO 1 — REGISTRAR NOVA DECISÃO
# ==========================================
with st.expander("➕ REGISTRAR NOVA DECISÃO", expanded=False):
    with st.form("form_decisao", clear_on_submit=True):
        c1, c2, c3 = st.columns([3, 2, 2])
        
        with c1:
            opcoes = get_opcoes_selectbox()
            selecao = st.selectbox("Ativo:", opcoes)
            ticker_manual = st.text_input("Ou digite o ticker manualmente:", "").strip().upper()
            
        with c2:
            tipo_decisao = st.selectbox("Tipo de Operação:", ['COMPRA', 'VENDA', 'AUMENTO POSIÇÃO', 'REDUÇÃO'])
            data_dec = st.date_input("Data da Decisão", datetime.date.today())
            
        with c3:
            preco_dec = st.number_input("Preço na Decisão (R$ / $):", min_value=0.0, format="%.2f")
            qtd_dec = st.number_input("Quantidade:", min_value=0.0, format="%.4f")
            
        tese_dec = st.text_area("Tese de Investimento (Porquê comprou/vendeu? O que esperava?):", height=100)
        
        btn_salvar = st.form_submit_button("💾 REGISTRAR DECISÃO", type="primary")
        
        if btn_salvar:
            ticker_final = ticker_manual if ticker_manual else ticker_from_label(selecao)
            if not ticker_final or not tese_dec or preco_dec <= 0:
                st.error("Preencha o ticker, o preço válido e a tese de investimento.")
            else:
                registrar_decisao(ticker_final, tipo_decisao, data_dec.isoformat(), preco_dec, qtd_dec, tese_dec)
                st.success("✅ Decisão registada com sucesso no seu Diário de Bordo!")
                st.rerun()

# ==========================================
# SEÇÃO 2 E 3 — HISTÓRICO E ESTATÍSTICAS
# ==========================================
decisoes = listar_decisoes()

if not decisoes:
    st.info("O seu Diário de Decisões está vazio. Registe a sua primeira operação acima.")
    st.stop()

st.markdown("---")

# Calcular retrospectiva ao vivo
with st.spinner("Atualizando preços para auditar resultados..."):
    dados_tabela = []
    acertos = 0
    erros = 0
    neutros = 0
    total_avaliados = 0
    retornos_compra = []
    
    for d in decisoes:
        t = d['ticker']
        try:
            preco_atual = yf.Ticker(t).fast_info.last_price
        except:
            preco_atual = 0.0
            
        retorno_pct = ((preco_atual / d['preco_decisao']) - 1) * 100 if d['preco_decisao'] and preco_atual else 0.0
        
        # Inverte o sinal de retorno se for venda (se vendeu e caiu, foi uma boa decisão)
        if d['tipo'] in ['VENDA', 'REDUÇÃO']:
            retorno_pct = -retorno_pct

        data_d = datetime.datetime.strptime(d['data_decisao'], "%Y-%m-%d").date()
        dias_passados = (datetime.date.today() - data_d).days
        
        # Contagem para estatísticas
        res = d['resultado']
        if res == 'ACERTO':
            acertos += 1
            total_avaliados += 1
        elif res == 'ERRO':
            erros += 1
            total_avaliados += 1
        elif res == 'NEUTRO':
            neutros += 1
            total_avaliados += 1
            
        if d['tipo'] == 'COMPRA':
            retornos_compra.append(retorno_pct)
            
        dados_tabela.append({
            'ID': d['id'],
            'Ticker': t,
            'Tipo': d['tipo'],
            'Data': d['data_decisao'],
            'Preço Decisão': d['preco_decisao'],
            'Preço Atual': preco_atual,
            'Retorno %': retorno_pct,
            'Dias': dias_passados,
            'Tese': d['tese'][:50] + "..." if len(d['tese']) > 50 else d['tese'],
            'Resultado': res if res else '⏳ AGUARDANDO'
        })

df_decisoes = pd.DataFrame(dados_tabela)

# --- Exibir Estatísticas ---
st.markdown("#### 📊 ESTATÍSTICAS DE ACERTO (TRACK RECORD)")
c_e1, c_e2, c_e3, c_e4 = st.columns(4)

taxa_acerto = (acertos / total_avaliados * 100) if total_avaliados > 0 else 0
retorno_medio_compra = sum(retornos_compra) / len(retornos_compra) if retornos_compra else 0
melhor_decisao = df_decisoes['Retorno %'].max() if not df_decisoes.empty else 0
pior_decisao = df_decisoes['Retorno %'].min() if not df_decisoes.empty else 0

c_e1.metric("Taxa de Acerto (Avaliadas)", f"{taxa_acerto:.1f}%", f"{total_avaliados} decisões julgadas")
c_e2.metric("Retorno Médio (Compras)", f"{retorno_medio_compra:+.2f}%")
c_e3.metric("Melhor Decisão Ativa", f"{melhor_decisao:+.2f}%")
c_e4.metric("Pior Decisão Ativa", f"{pior_decisao:+.2f}%")

st.markdown("<br>", unsafe_allow_html=True)

# --- Exibir Tabela de Histórico ---
st.markdown("#### 📜 HISTÓRICO DE OPERAÇÕES")

def formatar_tabela(val):
    if type(val) in [float, int]:
        color = '#00FF00' if val > 0 else ('#FF0000' if val < 0 else '#888888')
        return f'color: {color}; font-weight: bold;'
    return ''

st.dataframe(
    df_decisoes.drop(columns=['ID']).style.applymap(formatar_tabela, subset=['Retorno %']).format({
        'Preço Decisão': '{:.2f}', 'Preço Atual': '{:.2f}', 'Retorno %': '{:+.2f}%'
    }),
    use_container_width=True, hide_index=True
)

# --- Avaliar/Atualizar Resultado Manualmente ---
with st.expander("⚖️ JULGAR UMA DECISÃO (Atualizar Status)"):
    c_u1, c_u2, c_u3 = st.columns([2, 2, 2])
    with c_u1:
        id_selecionado = st.selectbox("Selecione o ID da Decisão:", df_decisoes['ID'].tolist())
    with c_u2:
        novo_status = st.selectbox("Veredicto:", ['ACERTO', 'ERRO', 'NEUTRO', '⏳ AGUARDANDO'])
    with c_u3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("ATUALIZAR RESULTADO", type="primary", use_container_width=True):
            status_db = None if novo_status == '⏳ AGUARDANDO' else novo_status
            atualizar_resultado(id_selecionado, status_db)
            st.success("Julgamento atualizado!")
            st.rerun()

# ==========================================
# SEÇÃO 4 — ANÁLISE IA DO COMPORTAMENTO
# ==========================================
st.markdown("---")
st.markdown("#### 🧠 MENTORIA DE INVESTIMENTOS VIA IA")

if st.button("REVISAR OS MEUS PADRÕES DE DECISÃO COM IA", type="primary"):
    with st.spinner("A analisar vieses cognitivos e padrões comportamentais..."):
        try:
            df_revisao = df_decisoes.head(10).drop(columns=['ID'])
            csv_dados = df_revisao.to_csv(index=False, float_format='%.2f')
            
            client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
            prompt = f"""
            Você é um mentor de investimentos e analista comportamental (estilo Daniel Kahneman). 
            Analise o histórico das últimas decisões do investidor abaixo e identifique padrões de comportamento, 
            vieses cognitivos, pontos fortes e erros recorrentes.
            
            TABELA DE DECISÕES:
            {csv_dados}
            
            Escreva em português, usando formatação markdown limpa:
            1. **Padrão de Sucesso**: O que o investidor costuma fazer de certo nas decisões marcadas como "ACERTO" ou com alto retorno?
            2. **Padrão de Erro**: O que costuma falhar nas decisões de "ERRO" ou de retorno negativo? (As teses eram fracas? Entrou tarde?)
            3. **Viés Comportamental Principal**: Identifique o viés mais provável (ex: ancoragem, FOMO, aversão à perda, excesso de confiança).
            4. **Plano de Ação**: Uma sugestão prática de melhoria no processo de decisão para a próxima semana.
            
            Seja direto, crítico e construtivo. Não valide emoções, baseie-se na tese vs resultado.
            """
            resposta = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
            st.info(resposta.text)
        except Exception as e:
            st.error(f"Falha ao conectar com o mentor de IA: {e}")