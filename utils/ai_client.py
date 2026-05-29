"""
utils/ai_client.py
Cliente centralizado de IA — suporte a múltiplos providers.

Providers disponíveis:
  deepseek        → DeepSeek V4 Pro  (padrão)
  openai          → OpenAI GPT-4o
  gemini          → Google Gemini 2.5 Flash
  anthropic_compat→ Anthropic Claude (via compatibilidade OpenAI)

Estratégia de cache hit (120× mais barato que miss):
  - System prompts FIXOS nunca dinâmicos
  - Dados estáticos primeiro no prompt do usuário
  - Dados voláteis (preço, data) sempre no final
  - Temperatura baixa = respostas mais determinísticas = mais cache

Preços DeepSeek (USD por 1M tokens):
  Cache hit:  input $0.003625 | output $0.87
  Cache miss: input $0.435    | output $0.87
"""
from __future__ import annotations

import json
import re
import streamlit as st

from utils.logger import get_logger

logger = get_logger(__name__)

# ── Providers suportados ──────────────────────────────────────────────────────

PROVIDERS: dict[str, dict] = {
    'deepseek': {
        'base_url':      'https://api.deepseek.com/v1',
        'model_default': 'deepseek-chat',
        'secret_key':    'DEEPSEEK_API_KEY',
        'label':         'DeepSeek V4 Pro',
    },
    'openai': {
        'base_url':      'https://api.openai.com/v1',
        'model_default': 'gpt-4o',
        'secret_key':    'OPENAI_API_KEY',
        'label':         'OpenAI GPT-4o',
    },
    'gemini': {
        'base_url':      'https://generativelanguage.googleapis.com/v1beta/openai/',
        'model_default': 'gemini-2.5-flash',
        'secret_key':    'GEMINI_API_KEY',
        'label':         'Google Gemini 2.5 Flash',
    },
    'anthropic_compat': {
        'base_url':      'https://api.anthropic.com/v1',
        'model_default': 'claude-sonnet-4-5',
        'secret_key':    'ANTHROPIC_API_KEY',
        'label':         'Anthropic Claude Sonnet',
    },
}

# Constantes de compatibilidade (usadas internamente)
MODEL    = "deepseek-chat"
BASE_URL = "https://api.deepseek.com/v1"

# Free tier — Gemini Flash via chave global
FREE_MODEL    = "gemini-2.5-flash"
FREE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

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


# ── Tier detection ───────────────────────────────────────────────────────────

def get_tier_and_client(user_settings: dict = None) -> tuple:
    """
    Retorna (client, model, tier) onde tier é 'pro' ou 'free'.

    tier 'pro':  usuário tem chave própria configurada
    tier 'free': fallback para Gemini 2.5 Flash via GEMINI_API_KEY global.
                 Se GEMINI_API_KEY ausente, tenta DEEPSEEK_API_KEY global.
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError(
            "pacote `openai` não instalado. adicione `openai>=1.30.0` ao requirements.txt."
        )

    # ── Tier PRO: chave pessoal do usuário ────────────────────────────────────
    if user_settings:
        user_key = user_settings.get('ai_api_key', '').strip()
        if user_key:
            provider = user_settings.get('ai_provider', 'deepseek')
            model    = user_settings.get('ai_model', '')
            cfg      = PROVIDERS.get(provider, PROVIDERS['deepseek'])
            if not model:
                model = cfg['model_default']
            try:
                client = OpenAI(api_key=user_key, base_url=cfg['base_url'])
                logger.debug(f"[ai] tier=pro provider={provider} model={model}")
                return client, model, 'pro'
            except Exception as e:
                logger.warning(f"[ai] falha ao criar client pro: {e} — usando free tier")

    # ── Tier FREE: Gemini Flash global ────────────────────────────────────────
    gemini_key = st.secrets.get("GEMINI_API_KEY", "")
    if gemini_key:
        client = OpenAI(api_key=gemini_key, base_url=FREE_BASE_URL)
        logger.debug(f"[ai] tier=free model={FREE_MODEL}")
        return client, FREE_MODEL, 'free'

    # ── Fallback: DeepSeek global (chave legada) ──────────────────────────────
    deepseek_key = st.secrets.get("DEEPSEEK_API_KEY", "")
    if deepseek_key:
        client = OpenAI(api_key=deepseek_key, base_url=BASE_URL)
        logger.debug(f"[ai] tier=free (deepseek global) model={MODEL}")
        return client, MODEL, 'free'

    raise ValueError(
        "nenhuma chave de IA encontrada. configure GEMINI_API_KEY em secrets.toml "
        "(gratuita em aistudio.google.com) ou sua chave pessoal em Configurações → Minha IA."
    )


# ── Singleton do cliente global (DeepSeek padrão) ────────────────────────────

@st.cache_resource(show_spinner=False)
def get_ai_client():
    """
    Retorna o cliente OpenAI apontando para a API do DeepSeek.
    Instanciado uma única vez por sessão de servidor (cache_resource).
    Usado como fallback quando o usuário não configurou chave própria.
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


# ── Cliente por usuário (multi-provider, sem cache) ───────────────────────────

def get_ai_client_for_user(user_settings: dict) -> tuple:
    """
    Cria e retorna (client, model_name) para o provider configurado pelo usuário.

    Lógica de fallback para a API key:
      1. Chave pessoal do usuário (user_settings['ai_api_key'])
      2. Chave global do secrets.toml correspondente ao provider
      3. ValueError com mensagem legível ao usuário

    Não usa cache — o cliente é criado a cada chamada (barato, ~1ms).
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError(
            "pacote `openai` não instalado. adicione `openai>=1.30.0` ao requirements.txt."
        )

    provider   = user_settings.get('ai_provider', 'deepseek')
    model_name = user_settings.get('ai_model', '')
    user_key   = user_settings.get('ai_api_key', '').strip()

    cfg = PROVIDERS.get(provider, PROVIDERS['deepseek'])

    # model: usa o do user_settings; se ausente, pega o default do provider
    if not model_name:
        model_name = cfg['model_default']

    # api key: pessoal → global → erro
    api_key = user_key
    if not api_key:
        try:
            api_key = st.secrets.get(cfg['secret_key'], '')
        except Exception:
            api_key = ''

    if not api_key:
        raise ValueError(
            f"nenhuma api key encontrada para o provider '{cfg['label']}'. "
            f"configure em ⚙️ configurações → 🤖 minha ia."
        )

    client = OpenAI(api_key=api_key, base_url=cfg['base_url'])
    logger.debug(f"[ai_client] usando provider={provider} model={model_name}")
    return client, model_name


# ── Chamada principal — streaming ─────────────────────────────────────────────

def chamar_ia(
    prompt_usuario: str,
    system:         str   = SYSTEM_ANALISTA,
    max_tokens:     int   = 800,
    temperatura:    float = 0.3,
    stream:         bool  = True,
    thinking:       bool  = False,
    user_settings:  dict  = None,       # ← configurações pessoais do usuário
) -> str:
    """
    Envia uma mensagem ao provider de IA e retorna a resposta como string.

    Se user_settings for fornecido e contiver 'ai_api_key', usa o provider
    e a chave configurados pelo usuário. Caso contrário, usa o DeepSeek global.

    Se stream=True (padrão), renderiza o texto progressivamente dentro de um
    st.chat_message com estilo Courier New e cursor animado.

    Se thinking=True, ativa o modo de raciocínio profundo (budget: 2 000 tokens).
    Use apenas quando a qualidade justificar o custo extra de output.
    """
    # Respeita a preferência de modo salva pelo usuário
    _ai_modo = st.session_state.get('ai_modo_atual', 'free')
    if _ai_modo == 'free' or not (user_settings and user_settings.get('ai_api_key', '').strip()):
        user_settings = None

    try:
        client, model_name, tier = get_tier_and_client(user_settings)
    except (ValueError, RuntimeError) as e:
        st.error(str(e))
        return ""

    # Tier free: sem thinking, tokens reduzidos
    if tier == 'free':
        thinking   = False
        max_tokens = min(max_tokens, 600)

    mensagens = [
        {"role": "system", "content": system},
        {"role": "user",   "content": prompt_usuario},
    ]

    kwargs: dict = {
        "model":       model_name,
        "messages":    mensagens,
        "max_tokens":  max_tokens,
        "temperature": temperatura,
        "stream":      stream,
    }

    if thinking and tier == 'pro':
        kwargs["extra_body"] = {
            "thinking": {"type": "enabled", "budget_tokens": 2000}
        }

    try:
        if stream:
            return _stream_para_ui(client, kwargs, tier=tier)
        else:
            resp = client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""

    except Exception as e:
        st.error(f"erro no agente de ia: {e}")
        return ""


def _sanitizar_markdown(texto: str) -> str:
    if texto.count('**') % 2 != 0:
        texto += '**'
    asteriscos_simples = texto.count('*') - texto.count('**') * 2
    if asteriscos_simples % 2 != 0:
        texto += '*'
    if texto.count('`') % 2 != 0:
        texto += '`'
    return texto


def _stream_para_ui(client, kwargs: dict, tier: str = 'free') -> str:
    """
    Consome o stream de tokens e renderiza em tempo real na UI do Streamlit.
    Retorna o texto completo ao final.
    Exibe badge de tier (FREE · Gemini ou PRO) acima do texto.
    """
    if tier == 'pro':
        tier_badge = (
            '<span style="font-family:var(--font-ui,Inter,sans-serif);'
            ' font-size:0.58rem; font-weight:700; color:#FF8C00;'
            ' border:1px solid rgba(255,140,0,0.35);'
            ' padding:1px 7px; border-radius:10px;'
            ' margin-right:8px; vertical-align:middle;">PRO</span>'
        )
    else:
        tier_badge = (
            '<span style="font-family:var(--font-ui,Inter,sans-serif);'
            ' font-size:0.58rem; font-weight:600; color:#6B7280;'
            ' border:1px solid #2A2C3E;'
            ' padding:1px 7px; border-radius:10px;'
            ' margin-right:8px; vertical-align:middle;">FREE · Gemini</span>'
        )

    _STYLE_TEXTO = (
        "font-family:'Courier New',monospace;"
        " font-size:0.83rem;"
        " line-height:1.8;"
        " color:#C0C0C0;"
        " white-space:pre-wrap;"
        " word-wrap:break-word;"
        " overflow:visible;"
        " max-height:none;"
        " height:auto;"
        " display:block;"
    )

    texto_completo = ""

    with st.chat_message("assistant", avatar="⚡"):
        # Injetar CSS do cursor uma única vez fora do placeholder
        st.markdown(
            '<style>'
            '@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}'
            '.ft-cursor{animation:blink 1s infinite;color:#FF9900;}'
            '</style>',
            unsafe_allow_html=True,
        )
        with st.container():
            placeholder = st.empty()

            # Estado inicial: badge + cursor
            placeholder.markdown(
                f'<div style="margin-top:4px;">{tier_badge}'
                f'<span class="ft-cursor" style="font-family:\'Courier New\','
                f'monospace; font-size:0.83rem; color:#FF9900;">▋</span></div>',
                unsafe_allow_html=True,
            )

            resp_stream = client.chat.completions.create(**kwargs)

            for chunk in resp_stream:
                delta = chunk.choices[0].delta
                # thinking chunks não têm .content; ignorar
                if hasattr(delta, "content") and delta.content:
                    texto_completo += delta.content
                    _texto_render = _sanitizar_markdown(texto_completo)
                    placeholder.markdown(
                        f'<div style="margin-top:4px;">{tier_badge}'
                        f'<div style="{_STYLE_TEXTO}">'
                        f'{_texto_render}'
                        f'<span class="ft-cursor">▋</span></div></div>',
                        unsafe_allow_html=True,
                    )

            # Render final sem cursor (texto completo, sem sanitização)
            placeholder.markdown(
                f'<div style="margin-top:4px;">{tier_badge}'
                f'<div style="{_STYLE_TEXTO}">'
                f'{texto_completo}</div></div>',
                unsafe_allow_html=True,
            )

    return texto_completo


# ── Chamada JSON — saída estruturada ──────────────────────────────────────────

def chamar_ia_json(
    prompt_usuario: str,
    system:         str  = SYSTEM_ANALISTA,
    max_tokens:     int  = 600,
    user_settings:  dict = None,
) -> dict:
    """
    Chama o provider em modo JSON e retorna um dict Python.

    O prompt DEVE instruir o modelo a retornar JSON válido.
    Em caso de falha de parse, retorna {} e loga o erro no console.
    Temperatura fixada em 0.1 para máxima consistência e cache hit.
    """
    try:
        client, model_name, _tier = get_tier_and_client(user_settings)
    except (ValueError, RuntimeError) as e:
        logger.warning(f"[ai_client] chamar_ia_json: {e}")
        return {}

    mensagens = [
        {"role": "system", "content": system},
        {"role": "user",   "content": prompt_usuario},
    ]

    raw = "{}"
    try:
        resp = client.chat.completions.create(
            model=model_name,
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
