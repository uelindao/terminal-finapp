"""
utils/tickers.py
─────────────────────────────────────────────────────────────────────
Catálogo central de tickers do FinTerminal.
Importar daqui em todas as páginas — NUNCA hardcode tickers nas páginas.
"""

# ─────────────────────────────────────────────────────────────────────
# BRASIL — Carteira pessoal (formato yfinance)
# ─────────────────────────────────────────────────────────────────────

BR_INDICES = [
    "^BVSP",       # Ibovespa
    "BOVA11.SA",   # ETF Ibovespa
    "FIND11.SA",   # ETF Financeiro
    "DIVO11.SA",   # ETF Dividendos
]

BR_ACOES = [
    "ITUB4.SA",    # Itaú Unibanco
    "BBAS3.SA",    # Banco do Brasil
    "VALE3.SA",    # Vale
    "PETR4.SA",    # Petrobras PN
    "SMFT3.SA",    # Smartfit
    "CURY3.SA",    # Cury Construtora
    "AZZA3.SA",    # Azzas 2154 (ex-Arezzo)
    "CASH3.SA",    # Méliuz
]

BR_FIIS = [
    "XPML11.SA",   # XP Malls
    "CPTS11.SA",   # Capitânia Securities
    "RBRR11.SA",   # RBR Rendimento High Grade
    "LVBI11.SA",   # VBI Logístico
    "PORD11.SA",   # Polo Recebíveis
    "BRCO11.SA",   # Bresco Logística
    "PVBI11.SA",   # VBI Prime Properties
    "KNCR11.SA",   # Kinea Rendimentos
    "RBRX11.SA",   # RBR Alpha Multiestrategia
]

BRASIL_TODOS = BR_ACOES + BR_FIIS

BRASIL_LABELS = {
    "^BVSP":      "^BVSP — Ibovespa",
    "BOVA11.SA":  "BOVA11.SA — ETF Ibovespa",
    "FIND11.SA":  "FIND11.SA — ETF Financeiro",
    "DIVO11.SA":  "DIVO11.SA — ETF Dividendos",
    "ITUB4.SA":   "ITUB4.SA — Itaú Unibanco",
    "BBAS3.SA":   "BBAS3.SA — Banco do Brasil",
    "VALE3.SA":   "VALE3.SA — Vale",
    "PETR4.SA":   "PETR4.SA — Petrobras PN",
    "SMFT3.SA":   "SMFT3.SA — Smartfit",
    "CURY3.SA":   "CURY3.SA — Cury Construtora",
    "AZZA3.SA":   "AZZA3.SA — Azzas 2154",
    "CASH3.SA":   "CASH3.SA — Méliuz",
    "XPML11.SA":  "XPML11.SA — XP Malls (FII)",
    "CPTS11.SA":  "CPTS11.SA — Capitânia Securities (FII)",
    "RBRR11.SA":  "RBRR11.SA — RBR High Grade (FII)",
    "LVBI11.SA":  "LVBI11.SA — VBI Logístico (FII)",
    "PORD11.SA":  "PORD11.SA — Polo Recebíveis (FII)",
    "BRCO11.SA":  "BRCO11.SA — Bresco Logística (FII)",
    "PVBI11.SA":  "PVBI11.SA — VBI Prime Properties (FII)",
    "KNCR11.SA":  "KNCR11.SA — Kinea Rendimentos (FII)",
    "RBRX11.SA":  "RBRX11.SA — RBR Alpha (FII)",
}

# ─────────────────────────────────────────────────────────────────────
# XSTOCKS — Ações tokenizadas RWA (NYSE/NASDAQ)
# ─────────────────────────────────────────────────────────────────────

XSTOCKS_INDICES = [
    "IWM", "SPY", "QQQ", "VTI", "IEMG", "SCHF", 
    "SLV", "PALL", "PPLT", "COPX"
]

XSTOCKS_ACOES = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA", 
    "AMD", "INTC", "AVGO", "MRVL", "ORCL", "CRM", "CSCO", 
    "IBM", "HON", "APP", "PLTR", "CRWD", "JPM", "BAC", "GS", 
    "V", "MA", "BRK-B", "JNJ", "UNH", "LLY", "ABBV", "PFE", 
    "MRK", "ABT", "AZN", "NVO", "MDT", "TMO", "DHR", "KO", 
    "PEP", "MCD", "WMT", "HD", "PG", "PM", "CMCSA", "NFLX", 
    "XOM", "CVX", "ACN", "LIN", "COIN", "MSTR", "GME", 
    "HOOD", "OPEN", "AMBR", "BTBT", "IREN"
]

XSTOCKS_TODOS = XSTOCKS_INDICES + XSTOCKS_ACOES

XSTOCKS_LABELS = {
    "IWM":   "IWM — iShares Russell 2000",
    "SPY":   "SPY — SPDR S&P 500",
    "QQQ":   "QQQ — Invesco NASDAQ 100",
    "VTI":   "VTI — Vanguard Total Market",
    "IEMG":  "IEMG — iShares Emerging Markets",
    "AAPL":  "AAPL — Apple",
    "MSFT":  "MSFT — Microsoft",
    "NVDA":  "NVDA — Nvidia",
    "GOOGL": "GOOGL — Alphabet (Google)",
    "META":  "META — Meta Platforms",
    "AMZN":  "AMZN — Amazon",
    "TSLA":  "TSLA — Tesla",
    "AMD":   "AMD — Advanced Micro Devices",
    "INTC":  "INTC — Intel",
    "AVGO":  "AVGO — Broadcom",
    "MRVL":  "MRVL — Marvell Technology",
    "ORCL":  "ORCL — Oracle",
    "CRM":   "CRM — Salesforce",
    "CSCO":  "CSCO — Cisco",
    "IBM":   "IBM — IBM",
    "HON":   "HON — Honeywell",
    "APP":   "APP — Applovin",
    "PLTR":  "PLTR — Palantir",
    "CRWD":  "CRWD — Crowdstrike",
    "JPM":   "JPM — JPMorgan Chase",
    "BAC":   "BAC — Bank of America",
    "GS":    "GS — Goldman Sachs",
    "V":     "V — Visa",
    "MA":    "MA — Mastercard",
    "BRK-B": "BRK-B — Berkshire Hathaway B",
    "JNJ":   "JNJ — Johnson & Johnson",
    "UNH":   "UNH — UnitedHealth",
    "LLY":   "LLY — Eli Lilly",
    "ABBV":  "ABBV — AbbVie",
    "PFE":   "PFE — Pfizer",
    "MRK":   "MRK — Merck",
    "ABT":   "ABT — Abbott",
    "AZN":   "AZN — AstraZeneca",
    "NVO":   "NVO — Novo Nordisk",
    "MDT":   "MDT — Medtronic",
    "TMO":   "TMO — Thermo Fisher",
    "DHR":   "DHR — Danaher",
    "KO":    "KO — Coca-Cola",
    "PEP":   "PEP — PepsiCo",
    "MCD":   "MCD — McDonald's",
    "WMT":   "WMT — Walmart",
    "HD":    "HD — Home Depot",
    "PG":    "PG — Procter & Gamble",
    "PM":    "PM — Philip Morris",
    "CMCSA": "CMCSA — Comcast",
    "NFLX":  "NFLX — Netflix",
    "XOM":   "XOM — ExxonMobil",
    "CVX":   "CVX — Chevron",
    "ACN":   "ACN — Accenture",
    "LIN":   "LIN — Linde",
    "COIN":  "COIN — Coinbase",
    "MSTR":  "MSTR — MicroStrategy",
    "GME":   "GME — GameStop",
    "HOOD":  "HOOD — Robinhood",
    "OPEN":  "OPEN — Opendoor",
    "AMBR":  "AMBR — Amber International",
    "BTBT":  "BTBT — Bit Brother",
    "IREN":  "IREN — Iris Energy",
    "SLV":   "SLV — iShares Silver",
    "PALL":  "PALL — Aberdeen Palladium",
    "PPLT":  "PPLT — Aberdeen Platinum",
    "COPX":  "COPX — Global X Copper Miners",
    "SCHF":  "SCHF — Schwab International",
}

# ─────────────────────────────────────────────────────────────────────
# SCREENER
# ─────────────────────────────────────────────────────────────────────
SCREENER_B3 = BR_ACOES + [
    "ABEV3.SA", "WEGE3.SA", "RENT3.SA", "PRIO3.SA", "GGBR4.SA",
    "RADL3.SA", "SUZB3.SA", "LREN3.SA", "MGLU3.SA", "EMBR3.SA",
    "CPLE6.SA", "EGIE3.SA", "TAEE11.SA", "EQTL3.SA", "JBSS3.SA",
    "BRFS3.SA", "SBSP3.SA", "VIVT3.SA", "CMIG4.SA", "KLBN11.SA",
]
SCREENER_B3 = list(dict.fromkeys(SCREENER_B3))

SCREENER_US = [t for t in XSTOCKS_ACOES if t not in ("GME","OPEN","AMBR","BTBT","IREN")]

# ─────────────────────────────────────────────────────────────────────
# FUNÇÕES DE APOIO
# ─────────────────────────────────────────────────────────────────────
def get_opcoes_selectbox():
    opcoes = []
    opcoes.append("─── 🇧🇷 AÇÕES BRASIL ───")
    for t in BR_ACOES: opcoes.append(BRASIL_LABELS.get(t, t))
    opcoes.append("─── 🇧🇷 FIIs BRASIL ───")
    for t in BR_FIIS: opcoes.append(BRASIL_LABELS.get(t, t))
    opcoes.append("─── 🌎 XSTOCKS (RWA) ───")
    for t in XSTOCKS_ACOES: opcoes.append(XSTOCKS_LABELS.get(t, t))
    opcoes.append("─── 📊 ETFs / ÍNDICES ───")
    for t in XSTOCKS_INDICES + BR_INDICES:
        label = XSTOCKS_LABELS.get(t, BRASIL_LABELS.get(t, t))
        opcoes.append(label)
    opcoes.append("── ✏️ OUTRO (digitar manualmente) ──")
    return opcoes

def ticker_from_label(label: str):
    if label.startswith("─") or "digitar" in label.lower():
        return None
    return label.split(" — ")[0].strip()

def get_opcoes_multiselect_backtesting():
    return (
        BR_ACOES + BR_FIIS +
        ["^BVSP", "^GSPC", "^IXIC"] +
        [t for t in XSTOCKS_ACOES if t in
         ("AAPL","MSFT","NVDA","GOOGL","META","AMZN","TSLA","JPM","KO","XOM")]
    )