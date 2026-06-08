import requests
from bs4 import BeautifulSoup
import yfinance as yf
from utils.logger import get_logger

logger = get_logger(__name__)

def buscar_dados_b3(ticker: str) -> dict:
    """extrai fundamentos reais do fundamentus mapeando a tabela de forma agressiva."""
    t = ticker.replace('.SA', '').strip().upper()
    url = f"https://www.fundamentus.com.br/detalhes.php?papel={t}"
    
    # disfarce de navegador atualizado para evitar bloqueios da cloudflare
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'pt-BR,pt;q=0.9'
    }
    
    res = {
        'nome': '—', 'setor': '—', 'p/l': None, 'p/vp': None, 
        'roe%': None, 'dy%': None, 'ev/ebitda': None, 'margem%': None, 'market_cap': 0
    }
    
    try:
        r = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # extrai todos os pares label/valor varrendo todas as linhas
        dados_tabela = {}
        for tr in soup.find_all('tr'):
            tds = tr.find_all('td')
            # a estrutura usa pares: [coluna_label, coluna_valor, coluna_label, coluna_valor]
            for i in range(0, len(tds) - 1, 2):
                # remove o ícone '?' e espaços em branco
                label = tds[i].text.replace('?', '').strip()
                valor = tds[i+1].text.strip()
                if label:
                    dados_tabela[label] = valor

        def get_num(chave):
            val = dados_tabela.get(chave, '—')
            if val in ['—', '-', '']: return None
            try:
                return float(val.replace('.', '').replace(',', '.').replace('%', ''))
            except Exception as e:
                logger.warning(f"[scrapers] falha ao converter '{chave}'='{val}' para float: {e}")
                return None

        res['nome'] = dados_tabela.get('Empresa', '—').lower()
        res['setor'] = dados_tabela.get('Setor', '—').lower()
        res['p/l'] = get_num('P/L')
        res['p/vp'] = get_num('P/VP')
        res['ev/ebitda'] = get_num('EV / EBITDA')
        res['roe%'] = get_num('ROE')
        res['dy%'] = get_num('Div. Yield')
        res['margem%'] = get_num('Marg. Líquida')
        res['market_cap'] = get_num('Valor de mercado')
        
        res = validar_fundamentos(res)

        # fallback: se qualidade baixa OU múltiplos críticos faltando, complementar com yfinance
        _criticos_ausentes = any(res.get(c) is None for c in ('p/l', 'p/vp', 'roe%'))
        if res.get('qualidade_dados', 0) < 60 or _criticos_ausentes:
            qualidade = res.get('qualidade_dados', 0)
            logger.info(f"[scrapers] fallback yfinance para {ticker} (qualidade: {qualidade}%, criticos ausentes: {_criticos_ausentes})")
            yf_dados = buscar_dados_us(ticker)
            for campo in ['p/l', 'p/vp', 'roe%', 'dy%', 'ev/ebitda', 'margem%']:
                if res.get(campo) is None and yf_dados.get(campo) is not None:
                    res[campo] = yf_dados[campo]
            if res['nome'] == '—' and yf_dados['nome'] != '—':
                res['nome'] = yf_dados['nome']
            # recalcular qualidade após fallback
            res = validar_fundamentos(res)

        return res
    except Exception as e:
        logger.warning(f"[scrapers] falha total no scraping do Fundamentus para {ticker}, usando fallback yfinance: {e}")
        return buscar_dados_us(ticker)


# ranges realistas para validação de dados fundamentalistas
RANGES_VALIDOS = {
    'p/l':      (-50.0,  500.0),
    'p/vp':     (0.0,    50.0),
    'roe%':     (-100.0, 300.0),
    'dy%':      (0.0,    30.0),
    'ev/ebitda':(-10.0,  100.0),
    'margem%':  (-200.0, 100.0),
}

def validar_fundamentos(dados: dict) -> dict:
    """
    Valida cada campo contra ranges realistas.
    Campos fora do range são zerados (None) para evitar distorção no score.
    Retorna o dict limpo e adiciona campo 'qualidade_dados' de 0 a 100.
    """
    campos_validos = 0
    campos_totais = len(RANGES_VALIDOS)

    for campo, (minimo, maximo) in RANGES_VALIDOS.items():
        val = dados.get(campo)
        if val is None:
            continue
        try:
            val = float(val)
            if minimo <= val <= maximo:
                campos_validos += 1
                dados[campo] = val
            else:
                dados[campo] = None  # dado fora do range — descartado
        except Exception as e:
            logger.warning(f"[scrapers] falha ao validar campo '{campo}' (valor={val}): {e}")
            dados[campo] = None

    dados['qualidade_dados'] = int((campos_validos / campos_totais) * 100)
    return dados


def buscar_dados_us(ticker: str) -> dict:
    """
    Busca fundamentos de ações US via yfinance.
    Usado como fonte primária para EUA e fallback para B3 quando Fundamentus falha.
    """
    res = {
        'nome': '—', 'setor': '—', 'p/l': None, 'p/vp': None,
        'roe%': None, 'dy%': None, 'ev/ebitda': None, 'margem%': None,
        'market_cap': 0, 'qualidade_dados': 0
    }
    try:
        acao = yf.Ticker(ticker)
        info = acao.info

        if not info or info.get('regularMarketPrice') is None:
            return res

        res['nome']       = info.get('longName', info.get('shortName', '—')).lower()
        res['setor']      = info.get('sector', info.get('industryDisp', '—')).lower()
        res['p/l']        = info.get('trailingPE') or info.get('forwardPE')
        res['p/vp']       = info.get('priceToBook')
        res['ev/ebitda']  = info.get('enterpriseToEbitda')
        _dy_raw = info.get('dividendYield') or info.get('trailingAnnualDividendYield')
        if _dy_raw is not None:
            _dy_raw = float(_dy_raw)
            if _dy_raw > 0.30:
                res['dy%'] = round(_dy_raw, 2)
            else:
                res['dy%'] = round(_dy_raw * 100, 2)
        else:
            res['dy%'] = None
        res['margem%']    = (info.get('profitMargins', 0) or 0) * 100
        res['market_cap'] = info.get('marketCap', 0) or 0

        roe_raw = info.get('returnOnEquity')
        res['roe%'] = (roe_raw * 100) if roe_raw is not None else None

        return validar_fundamentos(res)
    except Exception as e:
        logger.warning(f"[scrapers] falha ao buscar dados yfinance para {ticker}: {e}")
        return res