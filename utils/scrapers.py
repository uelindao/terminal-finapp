import requests
from bs4 import BeautifulSoup

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
            except:
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
        
        return res
    except:
        return res