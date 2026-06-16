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

# Lista ampliada de ativos B3 para rotação setorial mais rica
SCREENER_B3 = [
    # ── FINANCEIRO ──────────────────────────────────────────────────────
    "ABCB4.SA", "ABEV3.SA", "B3SA3.SA", "BBAS3.SA", "BBDC3.SA",
    "BBDC4.SA", "BBSE3.SA", "BPAC11.SA", "BRSR6.SA", "CIEL3.SA",
    "IRBR3.SA", "ITSA4.SA", "ITUB3.SA", "ITUB4.SA", "PSSA3.SA",
    "SANB11.SA", "WIZC3.SA",

    # ── ENERGIA / PETRÓLEO ───────────────────────────────────────────────
    "CSAN3.SA", "ENEV3.SA", "PETR3.SA", "PETR4.SA", "PRIO3.SA",
    "RECV3.SA", "RRRP3.SA", "VBBR3.SA", "UGPA3.SA", "DMMO3.SA",

    # ── UTILITIES (ELÉTRICO + SANEAMENTO) ───────────────────────────────
    "AURE3.SA", "CCEE3.SA", "CMIG4.SA", "CPFE3.SA", "CPLE3.SA",
    "CPLE6.SA", "EGIE3.SA", "ELET3.SA", "ELET6.SA", "ENGI11.SA",
    "EQTL3.SA", "CSMG3.SA", "SAPR11.SA", "SAPR4.SA", "SBSP3.SA",
    "TAEE11.SA", "TRPL4.SA",

    # ── MINERAÇÃO / SIDERURGIA / METALURGIA ─────────────────────────────
    "BRAP4.SA", "CSNA3.SA", "FESA4.SA", "GGBR4.SA", "GOAU4.SA",
    "USIM5.SA", "VALE3.SA",

    # ── CONSTRUÇÃO E ENGENHARIA ──────────────────────────────────────────
    "CYRE3.SA", "DIRR3.SA", "EVEN3.SA", "EZTC3.SA", "HBOR3.SA",
    "MDNE3.SA", "MRVE3.SA", "PLPL3.SA", "TEND3.SA", "TRIS3.SA",

    # ── AGRONEGÓCIO / ALIMENTOS / BEBIDAS ────────────────────────────────
    "ABEV3.SA", "BEEF3.SA", "BRFS3.SA", "JBSS3.SA", "MRFG3.SA",
    "MDIA3.SA", "SLCE3.SA", "SMTO3.SA", "CAML3.SA", "CRFB3.SA",

    # ── SAÚDE ────────────────────────────────────────────────────────────
    "FLRY3.SA", "HAPV3.SA", "HYPE3.SA", "PARD3.SA", "QUAL3.SA",
    "RADL3.SA", "RDOR3.SA", "ONCO3.SA", "DASA3.SA", "AALR3.SA",

    # ── TECNOLOGIA / SOFTWARE ────────────────────────────────────────────
    "INTB3.SA", "LWSA3.SA", "TOTS3.SA", "POSI3.SA", "CASH3.SA",
    "IFCM3.SA", "MOVI3.SA",

    # ── TELECOM ──────────────────────────────────────────────────────────
    "TIMS3.SA", "VIVT3.SA", "OIBR3.SA",

    # ── VAREJO / CONSUMO ─────────────────────────────────────────────────
    "ALOS3.SA", "ALPA4.SA", "ARZZ3.SA", "ASAI4.SA", "CEAB3.SA",
    "COGN3.SA", "CVCB3.SA", "GRND3.SA", "LREN3.SA", "MGLU3.SA",
    "NTCO3.SA", "ODPV3.SA", "PETZ3.SA", "SBFG3.SA", "SOMA3.SA",
    "VIVA3.SA", "VULC3.SA", "ZAMP3.SA", "AMOB3.SA", "BTOW3.SA",

    # ── INDÚSTRIA / MÁQUINAS / BENS DE CAPITAL ───────────────────────────
    "EMBR3.SA", "FRAS3.SA", "KEPL3.SA", "ROMI3.SA", "TUPY3.SA",
    "WEGE3.SA", "MYPK3.SA", "RAPT4.SA", "POMO4.SA", "FOBJ3.SA",

    # ── PAPEL E CELULOSE ─────────────────────────────────────────────────
    "DXCO3.SA", "KLBN11.SA", "SUZB3.SA",

    # ── TRANSPORTE E LOGÍSTICA ───────────────────────────────────────────
    "AZUL4.SA", "CCRO3.SA", "GOLL4.SA", "JSLG3.SA", "MULT3.SA",
    "RAIL3.SA", "RENT3.SA", "STBP3.SA", "VAMO3.SA", "PSSA3.SA",

    # ── IMOBILIÁRIO ──────────────────────────────────────────────────────
    "BRML3.SA", "IGTI11.SA", "IRDM11.SA",

    # ── EDUCAÇÃO ─────────────────────────────────────────────────────────
    "ANIM3.SA", "COGN3.SA", "SEER3.SA", "YDUQ3.SA",

    # ── QUÍMICOS / PETROQUÍMICOS ─────────────────────────────────────────
    "BRKM5.SA", "UNIP6.SA",

    # ── SEGUROS / PREVIDÊNCIA ────────────────────────────────────────────
    "BBSE3.SA", "CXSE3.SA", "SULA11.SA",

    # ── MINERAÇÃO NÃO-FERROSA ────────────────────────────────────────────
    "CBAV3.SA", "CMIN3.SA",
]

# Remove duplicatas mantendo ordem
SCREENER_B3 = list(dict.fromkeys(SCREENER_B3))

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

# Lista ampliada de ativos dos EUA para rotação setorial mais rica
SCREENER_US = [
    # ── TECNOLOGIA ───────────────────────────────────────────────────────
    "AAPL", "ADBE", "ADI", "AMAT", "AMD", "AMZN", "ANET", "ANSS",
    "ASML", "AVGO", "CDNS", "CRM", "CSCO", "FTNT", "GOOG", "GOOGL",
    "HPQ", "IBM", "INTC", "INTU", "KLAC", "LRCX", "META", "MSFT",
    "MU", "NOW", "NVDA", "ORCL", "PANW", "PYPL", "QCOM", "SNPS",
    "TXN", "ZBRA",

    # ── SAÚDE ────────────────────────────────────────────────────────────
    "ABBV", "ABT", "AMGN", "BAX", "BDX", "BIIB", "BMY", "BSX",
    "CI", "CVS", "DHR", "ELV", "GILD", "HCA", "HUM", "IDXX",
    "ISRG", "JNJ", "MDT", "MRK", "PFE", "REGN", "SYK", "TMO",
    "UNH", "VRTX", "ZBH",

    # ── FINANCEIRO ───────────────────────────────────────────────────────
    "AIG", "AMP", "AON", "AXP", "BAC", "BK", "BLK", "BRK-B",
    "C", "CB", "CFG", "CME", "COF", "DFS", "FI", "GS", "ICE",
    "JPM", "MCO", "MMC", "MS", "MSCI", "PGR", "SCHW", "SPGI",
    "TFC", "TRV", "USB", "V", "WFC",

    # ── CONSUMO DISCRICIONÁRIO ────────────────────────────────────────────
    "ABNB", "AMZN", "AZO", "BKNG", "CMG", "DHI", "EBAY", "F",
    "GM", "HD", "LEN", "LOW", "LVS", "MAR", "MCD", "MGM", "NKE",
    "ORLY", "PHM", "ROST", "SBUX", "TGT", "TJX", "TSLA", "YUM",

    # ── CONSUMO BÁSICO ────────────────────────────────────────────────────
    "CAG", "CL", "CLX", "COST", "EL", "GIS", "HSY", "K", "KMB",
    "KO", "MDLZ", "MKC", "MO", "PEP", "PG", "PM", "SJM", "STZ",
    "SYY", "WMT",

    # ── ENERGIA ──────────────────────────────────────────────────────────
    "BKR", "COP", "CVX", "DVN", "EOG", "FANG", "HAL", "HES",
    "KMI", "MPC", "MRO", "OKE", "OXY", "PSX", "SLB", "VLO",
    "WMB", "XOM",

    # ── INDÚSTRIA ────────────────────────────────────────────────────────
    "BA", "CAT", "CSX", "DE", "EMR", "ETN", "FDX", "GD", "GE",
    "HON", "ITW", "LMT", "MMM", "NOC", "NSC", "PH", "RTX", "SPCX",
    "TT", "UNP", "UPS", "WM",

    # ── MATERIAIS ────────────────────────────────────────────────────────
    "ALB", "APD", "CF", "DD", "ECL", "FCX", "FMC", "IP", "LIN",
    "MOS", "NEM", "NUE", "PKG", "PPG", "SHW",

    # ── UTILITIES ────────────────────────────────────────────────────────
    "AEE", "AEP", "AES", "AWK", "D", "DTE", "DUK", "ED", "EIX",
    "ES", "ETR", "EXC", "FE", "NEE", "NI", "PCG", "PEG", "SO",
    "SRE", "WEC", "XEL",

    # ── TELECOM ──────────────────────────────────────────────────────────
    "CHTR", "CMCSA", "DISH", "LUMN", "T", "TMUS", "VZ",

    # ── IMOBILIÁRIO (REITs) ────────────────────────────────────────────────
    "AMT", "ARE", "AVB", "CCI", "DLR", "EQR", "EXR", "IRM",
    "KIM", "O", "PSA", "PLD", "SBAC", "SPG", "WELL", "WY",
]

# Remove duplicatas
SCREENER_US = list(dict.fromkeys(SCREENER_US))

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