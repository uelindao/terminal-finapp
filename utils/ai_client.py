"""
utils/ai_client.py
Cliente centralizado de IA — DeepSeek V4 Pro.

Estratégia de cache hit (120× mais barato que miss):
  - System prompts FIXOS nunca dinâmicos
  - Dados estáticos primeiro no prompt do usuário
  - Dados voláteis (preço, data) sempre no final
  - Temperatura baixa = respostas mais determinísticas = mais cache

Preços (USD por 1M tokens):
  Cache hit:  input $0.003625 | output $0.87
  Cache miss: input $0.435    | output $0.87
"""
from __future__ import annotations

import json
import re
import streamlit as st

# ── Constantes ───────────────────────────────────────────────────────────────

MODEL = "deepseek-chat"           # alias estável do V3/V4 Pro no endpoint DeepSeek
BASE_URL = "https://api.deepseek.com/v1"

# ── System prompts FIXOS ─────────────────────────────────────────────────────
# NUNCA interpolar variáveis aqui — qualquer mudança quebra o cache hit.

SYSTEM_ANALISTA = (
    "você é um analista fundamentalista sênior especializado em ações brasileiras e americanas. "
    "seu estilo é direto, quantitativo e sem jargões desnecessários. "
    "sempre apresenta teses com dados concretos, múltiplos de valuation e contexto setorial. "
    "escreve em português do brasil, com todas as frases iniciando em letra minúscula. "
    "não usa emojis. não usa negrito ou markdown excessivo. "
    "estrutura respostas com tópicos curtos e objetivos."
)

SYSTEM_PORTFOLIO = (
    "você é um gestor de portfólio quantitativo com foco em risco e retorno ajustado. "
    "analisa carteiras usando métricas como sharpe, drawdown, correlação e var. "
    "recomendações são sempre práticas: o que comprar, vender ou manter, com raciocínio. "
    "escreve em português do brasil, iniciando frases com letra minúscula. "
    "não usa emojis. respostas concisas, em tópicos, sem rodeios."
)

SYSTEM_MACRO = (
    "você é um estrategista macro de um hedge fund global. "
    "interpreta dados econômicos — juros, inflação, câmbio, spreads de crédito — "
    "e traduz em implicações práticas para alocação de ativos. "
    "foco nos mercados brasileiro e americano, com visão global de riscos. "
    "escreve em português do brasil, iniciando frases com letra minúscula. "
    "não usa emojis. direto ao ponto, sem introduções desnecessárias."
)

SYSTEM_TESE = (
    "você é um analista sell-side especializado em elaborar teses de investimento. "
    "sua tese padrão: contexto do negócio → drivers de valor → riscos → valuation → veredicto. "
    "usa múltiplos (P/L, EV/EBITDA, P/VP, dividend yield) e compara com peers. "
    "escreve em português do brasil, iniciando frases com letra minúscula. "
    "não usa emojis. estrutura clara, leitura rápida."
)


# ── Singleton do cliente ──────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def get_ai_client():
    """
    Retorna o cliente OpenAI apontando para a API do DeepSeek.
    Instanciado uma única vez por sessão de servidor (cache_resource).
    """
    try:
        from openai import OpenAI
    except ImportError:
        st.error(
            "pacote `openai` não encontrado. "
            "adicione `openai>=1.30.0` ao requirements.txt e reinicie."
        )
        return None

    api_key = st.secrets.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        st.warning(
            "⚠️ `DEEPSEEK_API_KEY` não configurada em secrets.toml. "
            "adicione a chave para usar os recursos de ia."
        )
        return None

    return OpenAI(api_key=api_key, base_url=BASE_URL)


# ── Chamada principal — streaming ─────────────────────────────────────────────

def chamar_ia(
    prompt_usuario: str,
    system: str = SYSTEM_ANALISTA,
    max_tokens: int = 800,
    temperatura: float = 0.3,
    stream: bool = True,
    thinking: bool = False,
) -> str:
    """
    Envia uma mensagem ao DeepSeek e retorna a resposta como string.

    Se stream=True (padrão), renderiza o texto progressivamente dentro de um
    st.chat_message com estilo Courier New e cursor animado.

    Se thinking=True, ativa o modo de raciocínio profundo (budget: 2 000 tokens).
    Use apenas quando a qualidade justificar o custo extra de output.
    """
    client = get_ai_client()
    if client is None:
        return ""

    mensagens = [
        {"role": "system",  "content": system},
        {"role": "user",    "content": prompt_usuario},
    ]

    kwargs: dict = {
        "model":       MODEL,
        "messages":    mensagens,
        "max_tokens":  max_tokens,
        "temperature": temperatura,
        "stream":      stream,
    }

    if thinking:
        kwargs["extra_body"] = {
            "thinking": {"type": "enabled", "budget_tokens": 2000}
        }

    try:
        if stream:
            return _stream_para_ui(client, kwargs)
        else:
            resp = client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""

    except Exception as e:
        st.error(f"erro no agente de ia: {e}")
        return ""


def _stream_para_ui(client, kwargs: dict) -> str:
    """
    Consome o stream de tokens e renderiza em tempo real na UI do Streamlit.
    Retorna o texto completo ao final.
    """
    texto_completo = ""

    with st.chat_message("assistant", avatar="⚡"):
        placeholder = st.empty()

        # CSS do cursor piscante
        placeholder.markdown(
            '<style>'
            '@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }'
            '.ft-cursor { animation: blink 1s infinite; color:#FF9900; }'
            '</style>'
            '<div style="font-family:\'Courier New\',monospace; '
            'font-size:0.82rem; line-height:1.7; color:#ccc;">'
            '<span class="ft-cursor">▋</span></div>',
            unsafe_allow_html=True,
        )

        resp_stream = client.chat.completions.create(**kwargs)

        for chunk in resp_stream:
            delta = chunk.choices[0].delta
            # thinking chunks não têm .content; ignorar
            if hasattr(delta, "content") and delta.content:
                texto_completo += delta.content
                placeholder.markdown(
                    f'<div style="font-family:\'Courier New\',monospace; '
                    f'font-size:0.82rem; line-height:1.7; color:#ccc;">'
                    f'{texto_completo}'
                    f'<span class="ft-cursor">▋</span></div>',
                    unsafe_allow_html=True,
                )

        # Render final sem cursor
        placeholder.markdown(
            f'<div style="font-family:\'Courier New\',monospace; '
            f'font-size:0.82rem; line-height:1.7; color:#ccc;">'
            f'{texto_completo}</div>',
            unsafe_allow_html=True,
        )

    return texto_completo


# ── Chamada JSON — saída estruturada ──────────────────────────────────────────

def chamar_ia_json(
    prompt_usuario: str,
    system: str = SYSTEM_ANALISTA,
    max_tokens: int = 600,
) -> dict:
    """
    Chama o DeepSeek em modo JSON e retorna um dict Python.

    O prompt DEVE instruir o modelo a retornar JSON válido.
    Em caso de falha de parse, retorna {} e loga o erro no console.

    Temperatura fixada em 0.1 para máxima consistência e cache hit.
    """
    client = get_ai_client()
    if client is None:
        return {}

    mensagens = [
        {"role": "system",  "content": system},
        {"role": "user",    "content": prompt_usuario},
    ]

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=mensagens,
            max_tokens=max_tokens,
            temperature=0.1,
            stream=False,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"

        # Remove blocos markdown caso o modelo os adicione
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw.strip())

        return json.loads(raw)

    except json.JSONDecodeError as e:
        print(f"[ai_client] json parse error: {e} | raw: {raw[:200]}")
        return {}
    except Exception as e:
        st.error(f"erro no agente de ia (json): {e}")
        return {}


# ── Helpers de prompt — melhores práticas de cache ───────────────────────────

def montar_prompt_analise(
    ticker: str,
    dados_estaticos: str,
    dados_volateis: str,
) -> str:
    """
    Monta prompt de análise respeitando a ordem de cache hit:
      1. identificação do ativo (estática)
      2. dados fundamentais / históricos (estáticos)
      3. preços atuais / data (voláteis) — sempre no final

    Args:
        ticker:          símbolo do ativo (ex: WEGE3.SA)
        dados_estaticos: fundamentos, múltiplos, histórico — CSV ou texto
        dados_volateis:  cotação atual, variação do dia, data de referência
    """
    return (
        f"ativo: {ticker}\n\n"
        f"dados fundamentais e históricos:\n{dados_estaticos}\n\n"
        f"dados de mercado atuais:\n{dados_volateis}"
    )


def montar_prompt_portfolio(
    dados_carteira: str,
    contexto_macro: str,
    dados_volateis: str,
) -> str:
    """
    Ordem de cache: carteira (relativamente estática) → macro → dados voláteis.
    """
    return (
        f"composição da carteira:\n{dados_carteira}\n\n"
        f"contexto macroeconômico:\n{contexto_macro}\n\n"
        f"dados de mercado atuais:\n{dados_volateis}"
    )
