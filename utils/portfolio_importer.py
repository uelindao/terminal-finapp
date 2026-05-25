"""
utils/portfolio_importer.py
Importador de portfólio via CSV ou Excel.

Formato aceito (colunas obrigatórias):
  ticker       — código do ativo (ex: WEGE3, WEGE3.SA, AAPL)
  quantidade   — número de cotas/ações
  preco_medio  — preço médio de compra

Colunas opcionais (ignoradas se ausentes):
  nome         — nome da empresa (preenchido automaticamente se vazio)
  mercado      — "Brasil (B3)" ou "EUA" (detectado automaticamente)
  notas        — anotações pessoais sobre a posição

O arquivo aceita tanto vírgula quanto ponto-e-vírgula como separador.
Aceita ponto ou vírgula como decimal.
Ignora linhas com ticker vazio ou inválido.
"""

import io
import pandas as pd
from utils.logger import get_logger

logger = get_logger(__name__)

# Template para o usuário baixar
TEMPLATE_CSV = """ticker,quantidade,preco_medio,notas
WEGE3.SA,100,38.50,posição principal
ITUB4.SA,200,25.80,
AAPL,10,172.30,tech usa
MXRF11.SA,500,10.20,fii renda
"""


def detectar_mercado(ticker: str) -> str:
    """Detecta o mercado com base no ticker."""
    t = ticker.strip().upper()
    if t.endswith('.SA'):
        return 'Brasil (B3)'
    # Heurística: tickers BR sem .SA (usuário pode ter esquecido o sufixo).
    # Se tiver dígito nos dois últimos caracteres (PETR4, VALE3), provável B3.
    if len(t) <= 6 and any(c.isdigit() for c in t[-2:]):
        return 'Brasil (B3)'
    return 'EUA'


def normalizar_ticker(ticker: str) -> str:
    """
    Normaliza o ticker para o formato padrão do terminal.
    - Remove espaços
    - Uppercase
    - Adiciona .SA para ações BR detectadas sem sufixo
    """
    t = ticker.strip().upper()
    if not t:
        return ''

    mercado = detectar_mercado(t)
    if mercado == 'Brasil (B3)' and not t.endswith('.SA'):
        t = t + '.SA'

    return t


def parsear_numero(valor) -> float | None:
    """
    Parseia número aceitando tanto ponto quanto vírgula como separador decimal.
    Ex: "1.234,56" → 1234.56  |  "38,50" → 38.50  |  "172.30" → 172.30
    """
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    try:
        s = str(valor).strip()
        if ',' in s and '.' in s:
            # Formato brasileiro com milhar: 1.234,56
            s = s.replace('.', '').replace(',', '.')
        elif ',' in s:
            # Decimal com vírgula: 38,50
            s = s.replace(',', '.')
        return float(s)
    except Exception:
        return None


def importar_planilha(arquivo_bytes: bytes, nome_arquivo: str) -> dict:
    """
    Processa o arquivo uploaded e retorna dict com:
      - 'sucesso':  bool
      - 'posicoes': list[dict] com posições válidas
      - 'erros':    list[str] com linhas problemáticas
      - 'avisos':   list[str] com avisos não-críticos
      - 'total':    int total de linhas processadas
    """
    resultado: dict = {
        'sucesso':  False,
        'posicoes': [],
        'erros':    [],
        'avisos':   [],
        'total':    0,
    }

    try:
        nome_lower = nome_arquivo.lower()
        df = None

        # ── Leitura do arquivo ──────────────────────────────────────────────
        if nome_lower.endswith('.csv'):
            # Tenta combinações de encoding × separador até conseguir ≥ 2 colunas
            for encoding in ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']:
                for sep in [',', ';', '\t']:
                    try:
                        candidate = pd.read_csv(
                            io.BytesIO(arquivo_bytes),
                            sep=sep,
                            encoding=encoding,
                            dtype=str,
                            skip_blank_lines=True,
                        )
                        if len(candidate.columns) >= 2:
                            df = candidate
                            break
                    except Exception:
                        continue
                if df is not None:
                    break

        elif nome_lower.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(arquivo_bytes), dtype=str)

        else:
            resultado['erros'].append(
                "formato não suportado. use .csv ou .xlsx"
            )
            return resultado

        if df is None or df.empty:
            resultado['erros'].append("arquivo vazio ou não foi possível ler.")
            return resultado

        # ── Normaliza nomes de colunas ──────────────────────────────────────
        df.columns = (
            df.columns
            .str.strip()
            .str.lower()
            .str.replace(' ', '_', regex=False)
            .str.normalize('NFKD')
            .str.encode('ascii', errors='ignore')
            .str.decode('ascii')
        )

        # ── Mapeia variações de nomes de coluna ─────────────────────────────
        mapeamento_colunas = {
            'ticker':      ['ticker', 'ativo', 'papel', 'codigo', 'symbol'],
            'quantidade':  ['quantidade', 'qtd', 'qtde', 'quantity',
                            'cotas', 'acoes'],
            'preco_medio': ['preco_medio', 'preco', 'pm', 'custo_medio',
                            'price', 'preco_de_custo', 'custo'],
            'nome':        ['nome', 'empresa', 'name', 'descricao'],
            'notas':       ['notas', 'nota', 'obs', 'observacao', 'notes'],
        }

        colunas_encontradas: dict[str, str] = {}
        for campo, alternativas in mapeamento_colunas.items():
            for alt in alternativas:
                if alt in df.columns:
                    colunas_encontradas[campo] = alt
                    break

        # ── Verifica colunas obrigatórias ───────────────────────────────────
        obrigatorias = ['ticker', 'quantidade', 'preco_medio']
        faltando = [c for c in obrigatorias if c not in colunas_encontradas]
        if faltando:
            resultado['erros'].append(
                f"colunas obrigatórias não encontradas: {', '.join(faltando)}. "
                f"colunas detectadas: {', '.join(df.columns.tolist())}"
            )
            return resultado

        resultado['total'] = len(df)

        # ── Processa cada linha ─────────────────────────────────────────────
        for idx, row in df.iterrows():
            linha_num = idx + 2  # +2 = header + 1-indexed

            # Ticker
            ticker_raw = str(row[colunas_encontradas['ticker']]).strip()
            if not ticker_raw or ticker_raw.lower() in (
                'nan', 'none', '', 'ticker', 'ativo'
            ):
                continue  # linha vazia ou header duplicado

            ticker = normalizar_ticker(ticker_raw)
            if not ticker:
                resultado['erros'].append(
                    f"linha {linha_num}: ticker inválido '{ticker_raw}'"
                )
                continue

            # Quantidade
            qtd = parsear_numero(row[colunas_encontradas['quantidade']])
            if qtd is None or qtd <= 0:
                resultado['erros'].append(
                    f"linha {linha_num}: quantidade inválida para {ticker}"
                )
                continue

            # Preço médio
            pm = parsear_numero(row[colunas_encontradas['preco_medio']])
            if pm is None or pm <= 0:
                resultado['erros'].append(
                    f"linha {linha_num}: preço médio inválido para {ticker}"
                )
                continue

            # Campos opcionais
            nome = ''
            if 'nome' in colunas_encontradas:
                v = str(row[colunas_encontradas['nome']]).strip()
                if v.lower() not in ('nan', 'none', ''):
                    nome = v

            notas = ''
            if 'notas' in colunas_encontradas:
                v = str(row[colunas_encontradas['notas']]).strip()
                if v.lower() not in ('nan', 'none', ''):
                    notas = v

            mercado = detectar_mercado(ticker)

            resultado['posicoes'].append({
                'ticker':      ticker,
                'nome':        nome or ticker.replace('.SA', ''),
                'quantidade':  qtd,
                'preco_medio': pm,
                'mercado':     mercado,
                'notas':       notas,
            })

        if resultado['posicoes']:
            resultado['sucesso'] = True
            logger.info(
                f"[importer] {len(resultado['posicoes'])} posições "
                f"importadas de {nome_arquivo}"
            )
        else:
            resultado['erros'].append(
                "nenhuma posição válida encontrada no arquivo."
            )

    except Exception as e:
        logger.error(f"[importer] erro ao processar arquivo: {e}")
        resultado['erros'].append(f"erro ao processar: {e}")

    return resultado
