# =====================================================================
# rwa & mercado global tokenizado (ondo + xstocks/backed)
# =====================================================================

ONDO_TOKENS = [
    "AAPLon", "NVDAon", "TSLAon", "AMZNon", "MSFTon", "GOOGLon", "INTCon", 
    "MUon", "AMDon", "TSMon", "QCOMon", "ORCLon", "ARMon", "SMCIon", 
    "MRVLon", "SNDKon", "CRWVon", "SNOWon", "COHRon", "IONQON", "RGTION",
    "COINon", "MSTRon", "CRCLon", "IRENon", "NBISON",
    "XOMon", "ETNon", "GEVON", "MPon", "NVOon", "HIMSon", "RKLBon", "ASTSon",
    "BABAon", "BIDUon", "NIOon", "JDon", "PDDon", "NTESon",
    "SPYon", "QQQon", "TQQQon", "SQQQon", "TLTon", "EEMON", "EFAON", 
    "INDAON", "EWYon", "FFOGon",
    "IAUon", "FGDLon", "SLVon", "USOon", "URAon"
]

XSTOCKS_BACKED = [
    "AAPLx", "bAAPL", "bMSFT", "GOOGLx", "bGOOGL", "AMZNx", "NVDAx", "TSLAx",
    "MSTRx", "COINx", "bCOIN", "PLTRx", "SNOWx", "NIOx", "bNIO", "BABAx",
    "IB01x", "bIB01", "CSPXx", "bCSPX", "bVUAA"
]

XSTOCKS_TODOS = sorted(ONDO_TOKENS + XSTOCKS_BACKED)
XSTOCKS_LABELS = [f"{t} — ondo finance" if t in ONDO_TOKENS else f"{t} — backed asset" for t in XSTOCKS_TODOS]

XSTOCKS_INDICES = [
    "SPYon", "QQQon", "TQQQon", "SQQQon", "TLTon", "EEMON", "EFAON", 
    "INDAON", "EWYon", "FFOGon", "IB01x", "bIB01", "CSPXx", "bCSPX", "bVUAA"
]

# =====================================================================
# mercado brasileiro (b3)
# =====================================================================

# As ~130 empresas mais líquidas e relevantes da B3 (IBOV + IBrX100)
SCREENER_B3 = [
    "ABEV3.SA", "ALOS3.SA", "ALPA4.SA", "ANIM3.SA", "ARZZ3.SA", "ASAI4.SA", "AURE3.SA", "AZUL4.SA", 
    "B3SA3.SA", "BBAS3.SA", "BBDC3.SA", "BBDC4.SA", "BBSE3.SA", "BEEF3.SA", "BPAC11.SA", "BRAP4.SA", 
    "BRFS3.SA", "BRKM5.SA", "BRSR6.SA", "CCRO3.SA", "CEAB3.SA", "CMIG4.SA", "COGN3.SA", "CPFE3.SA", 
    "CPLE3.SA", "CPLE6.SA", "CRFB3.SA", "CSAN3.SA", "CSMG3.SA", "CSNA3.SA", "CVCB3.SA", "CYRE3.SA", 
    "DIRR3.SA", "DXCO3.SA", "EGIE3.SA", "ELET3.SA", "ELET6.SA", "EMBR3.SA", "ENEV3.SA", "ENGI11.SA", 
    "EQTL3.SA", "EZTC3.SA", "FESA4.SA", "FLRY3.SA", "FRAS3.SA", "GGBR4.SA", "GOAU4.SA", "GOLL4.SA", 
    "GRND3.SA", "HAPV3.SA", "HYPE3.SA", "IGTI11.SA", "INTB3.SA", "IRBR3.SA", "ITSA4.SA", "ITUB3.SA", 
    "ITUB4.SA", "JBSS3.SA", "JSLG3.SA", "KEPL3.SA", "KLBN11.SA", "LREN3.SA", "LWSA3.SA", "MDIA3.SA", 
    "MGLU3.SA", "MOVI3.SA", "MRFG3.SA", "MRVE3.SA", "MULT3.SA", "MYPK3.SA", "NTCO3.SA", "ODPV3.SA", 
    "PARD3.SA", "PETR3.SA", "PETR4.SA", "PETZ3.SA", "POMO4.SA", "PRIO3.SA", "PSSA3.SA", "PTBL3.SA", 
    "QUAL3.SA", "RADL3.SA", "RAPT4.SA", "RCSL3.SA", "RDOR3.SA", "RECV3.SA", "RENT3.SA", "ROMI3.SA", 
    "RRRP3.SA", "SANB11.SA", "SAPR11.SA", "SAPR4.SA", "SBFG3.SA", "SBSP3.SA", "SLCE3.SA", "SMTO3.SA", 
    "SOMA3.SA", "STBP3.SA", "SUZB3.SA", "TAEE11.SA", "TASA4.SA", "TEND3.SA", "TIMS3.SA", "TOTS3.SA", 
    "TRPL4.SA", "TUPY3.SA", "UGPA3.SA", "UNIP6.SA", "USIM5.SA", "VALE3.SA", "VAMO3.SA", "VBBR3.SA", 
    "VIVA3.SA", "VIVT3.SA", "VULC3.SA", "WEGE3.SA", "YDUQ3.SA", "ZAMP3.SA"
]

# Os ~70 fundos imobiliários mais líquidos do IFIX
FII_TODOS = [
    "ALZR11.SA", "ARRI11.SA", "BARI11.SA", "BCFF11.SA", "BRCO11.SA", "BRCR11.SA", "BTLG11.SA", 
    "CACR11.SA", "CPTS11.SA", "CVBI11.SA", "DEVA11.SA", "FEXC11.SA", "GARE11.SA", "GTWR11.SA", 
    "HABT11.SA", "HCTR11.SA", "HFOF11.SA", "HGBS11.SA", "HGCR11.SA", "HGLG11.SA", "HGRE11.SA", 
    "HGRU11.SA", "HSML11.SA", "HTMX11.SA", "IRDM11.SA", "JSRE11.SA", "KFOF11.SA", "KNCR11.SA", 
    "KNHY11.SA", "KNIP11.SA", "KNRI11.SA", "KNSC11.SA", "LVBI11.SA", "MALL11.SA", "MCCI11.SA", 
    "MCHF11.SA", "MXRF11.SA", "OUJP11.SA", "PVBI11.SA", "RBRF11.SA", "RBRR11.SA", "RBRY11.SA", 
    "RBVA11.SA", "RCRB11.SA", "RECR11.SA", "RECT11.SA", "RZAK11.SA", "RZTR11.SA", "SARE11.SA", 
    "SNCI11.SA", "SNFF11.SA", "TGAR11.SA", "TRXF11.SA", "URPR11.SA", "VCJR11.SA", "VGHF11.SA", 
    "VGIP11.SA", "VGIR11.SA", "VILG11.SA", "VINO11.SA", "VISC11.SA", "VTLG11.SA", "XPCI11.SA", 
    "XPIN11.SA", "XPLG11.SA", "XPML11.SA", "XPPR11.SA", "XPSF11.SA"
]

BR_INDICES = ["BOVA11.SA", "SMAL11.SA", "IVVB11.SA", "HASH11.SA", "NASH11.SA", "DIVO11.SA"]

BRASIL_TODOS = sorted(list(set(SCREENER_B3 + BR_INDICES + FII_TODOS)))
BR_LABELS = [f"{t} — b3 (brasil)" for t in BRASIL_TODOS]

# =====================================================================
# mercado eua (ações diretas via yahoo finance)
# =====================================================================

# As ~130 maiores empresas dos EUA (Pesos relevantes do S&P500 e Nasdaq 100)
SCREENER_US = [
    "AAPL", "ABBV", "ABT", "ACN", "ADBE", "ADI", "ADP", "AMAT", "AMD", "AMGN", "AMT", "AMZN", 
    "AON", "APH", "ASML", "AVGO", "AXP", "BA", "BAC", "BDX", "BK", "BLK", "BMY", "BRK-B", "C", 
    "CAT", "CB", "CDNS", "CI", "CME", "CMG", "CMCSA", "COF", "COP", "COST", "CRM", "CSCO", "CSX", 
    "CTAS", "CVS", "CVX", "DHR", "DIS", "DUK", "EOG", "ELV", "EMR", "ETN", "F", "FCX", "FI", "GD", 
    "GE", "GILD", "GM", "GOOG", "GOOGL", "GPN", "GS", "HD", "HON", "IBM", "ICE", "INTC", "INTU", 
    "ISRG", "ITW", "JNJ", "JPM", "KLAC", "KMB", "KO", "LIN", "LLY", "LMT", "LOW", "LRCX", "MA", 
    "MAR", "MCD", "MCO", "MDT", "META", "MMC", "MMM", "MO", "MPC", "MRK", "MS", "MSFT", "MU", 
    "NEE", "NFLX", "NKE", "NOC", "NOW", "NVDA", "ORCL", "PANW", "PEP", "PFE", "PG", "PGR", "PH", 
    "PM", "PSX", "PYPL", "QCOM", "RTX", "SBUX", "SCHW", "SHW", "SLB", "SNPS", "SO", "SPGI", "SYK", 
    "T", "TGT", "TJX", "TMO", "TMUS", "TSLA", "TXN", "UNH", "UNP", "UPS", "USB", "V", "VRTX", "VZ", 
    "WFC", "WM", "WMT", "XOM"
]

# =====================================================================
# utilitários
# =====================================================================

def get_opcoes_selectbox():
    """retorna a lista combinada e formatada para o selectbox principal."""
    opcoes = []
    opcoes.append("── brasil (b3) ──")
    opcoes.extend(BR_LABELS)
    
    opcoes.append("── eua (xstocks / ondo) ──")
    for t in ONDO_TOKENS:
        opcoes.append(f"{t} — ondo finance")
    for t in XSTOCKS_BACKED:
        opcoes.append(f"{t} — backed asset")

    opcoes.append("── ✏️ outro (digitar manualmente) ──")
    return opcoes

def ticker_from_label(label: str) -> str:
    """extrai o ticker limpo da string do selectbox."""
    if not label or label.startswith("─") or label.startswith("✏️"):
        return ""
    return label.split(" — ")[0].strip()

def mapear_ticker_base(ticker: str) -> str:
    """
    Converte um ticker RWA (tokenizado) no seu ticker base do Yahoo Finance.
    Ex: 'AAPLx' -> 'AAPL', 'bNVDA' -> 'NVDA', 'TSLAon' -> 'TSLA'
    """
    t = ticker.strip()
    
    # 1. Overrides específicos (Casos onde o ticker base é diferente do nome do token)
    excecoes = {
        "BRK.Bx": "BRK-B",   # Yahoo usa hífen para classes de ações
        "bCSPX": "CSPX.L",   # ETF S&P 500 em Londres
        "bIB01": "IB01.L",   # Tesouro Americano 0-1 ano
        "EEMON": "EEM",      # MSCI Emerging Markets
        "EFAON": "EFA",      # MSCI EAFE
        "IAUon": "IAU",      # Gold Trust
        "FGDLon": "FGDL",
        "SLVon": "SLV",
        "USOon": "USO",
        "URAon": "URA",
        "INDAON": "INDA",
        "EWYon": "EWY",
        "FFOGon": "FFOG"
    }
    
    if t in excecoes:
        return excecoes[t]
        
    if t.endswith("on"):
        return t[:-2]
    elif t.endswith("x"):
        return t[:-1]
    elif t.startswith("b") and len(t) > 1 and t[1].isupper():
        return t[1:]
        
    return t