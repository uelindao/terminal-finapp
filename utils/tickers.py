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
    "AAPLx", "bAAPL", "bMSFT", "GOOGLx", "bGOOGL", "AMZNx", "NVDAx", "bNVDA", 
    "TSLAx", "bTSLA", "AMDx", "AVGOx", "ASMLx", "CSCOx", "ADBEx", "CRWDx", 
    "APPx", "ANETx", "DELLx", "AMATx", "Tx", "CMCSAx", "DUOLx", "ASTSx", "bNIU",
    "COINx", "bCOIN", "MSTRx", "bMSTR", "BTBTx", "FUFUx", "BTGOx", "BMNRx", 
    "BLSHx", "CLSKx", "CORZx", "APLDx",
    "BLKx", "BACx", "BRK.Bx", "AXPx", "CRCLx",
    "ABTx", "ABBVx", "AZNx", "LLYx", "DHRx", "CVXx", "CEGx", "ETNx", "KOx", 
    "COSTx", "BKNGx", "EBAYx", "bGME",
    "bCSPX", "SPYx", "IEMGx", "bIB01", "bIBTA", "bZPR1", "bERNA", "bERNX", 
    "bC3M", "bHIGH", "bCSBGC3", "DFDVx",
    "PALLx", "PPLTx"
]

RWA_TODOS = ONDO_TOKENS + XSTOCKS_BACKED

# compatibilidade com o código anterior (agora mapeia para a lista rwa gigante)
XSTOCKS_TODOS = RWA_TODOS
SCREENER_US = RWA_TODOS
XSTOCKS_INDICES = ["SPYon", "QQQon", "TLTon", "bCSPX", "SPYx", "IEMGx", "bIB01"]

# ─────────────────────────────────────────────────────────────────────
# brasil — organizado por setor (formato yfinance, sufixo .sa)
# ─────────────────────────────────────────────────────────────────────

# ── energia e petróleo ───────────────────────────────────────────────
BR_ENERGIA = [
    "PETR3.SA", "PETR4.SA", "PRIO3.SA", "CSAN3.SA", "UGPA3.SA", 
    "VBBR3.SA", "RECV3.SA", "RRRP3.SA", "BRAV3.SA", "EGIE3.SA",
]

# ── mineração e siderurgia ───────────────────────────────────────────
BR_MINERACAO = [
    "VALE3.SA", "GGBR3.SA", "GGBR4.SA", "GOAU3.SA", "GOAU4.SA", 
    "CSNA3.SA", "CMIN3.SA", "USIM3.SA", "USIM5.SA", "FESA4.SA",
    "BRAP4.SA", "CBAV3.SA"
]

# ── financeiro — bancos ───────────────────────────────────────────────
BR_BANCOS = [
    "ITUB3.SA", "ITUB4.SA", "ITSA3.SA", "ITSA4.SA", "BBAS3.SA", 
    "BBDC3.SA", "BBDC4.SA", "SANB3.SA", "SANB4.SA", "SANB11.SA", 
    "BRSR3.SA", "BRSR6.SA", "BPAC3.SA", "BPAC11.SA", "BMGB4.SA",
    "ABCB4.SA"
]

# ── financeiro — seguros, bolsa e outros ──────────────────────────────
BR_FINANCEIRO = [
    "B3SA3.SA", "BBSE3.SA", "CXSE3.SA", "PSSA3.SA", "WIZC3.SA", 
    "XPBR31.SA", "IRBR3.SA", "CIEL3.SA"
]

# ── consumo e varejo ──────────────────────────────────────────────────
BR_CONSUMO = [
    "MGLU3.SA", "LREN3.SA", "AZZA3.SA", "SBFG3.SA", "VIVA3.SA", 
    "NTCO3.SA", "ALPA3.SA", "ALPA4.SA", "AMAR3.SA", "GUAR3.SA", 
    "PETZ3.SA", "SMFT3.SA", "MOVI3.SA", "ASAI3.SA", "CRFB3.SA", 
    "PCAR3.SA", "BHIA3.SA", "CEAB3.SA"
]

# ── alimentos, bebidas e agro ─────────────────────────────────────────
BR_ALIMENTOS = [
    "ABEV3.SA", "JBSS3.SA", "BEEF3.SA", "BRFS3.SA", "MDIA3.SA", 
    "CAML3.SA", "SLCE3.SA", "AGRO3.SA", "SMTO3.SA", "TTEN3.SA",
    "MRFG3.SA"
]

# ── indústria e bens de capital ────────────────────────────────────────
BR_INDUSTRIA = [
    "WEGE3.SA", "EMBR3.SA", "TUPY3.SA", "ROMI3.SA", "POMO3.SA", 
    "POMO4.SA", "INTB3.SA", "KEPL3.SA", "MYPK3.SA", "SHUL4.SA"
]

# ── saúde ────────────────────────────────────────────────────────────
BR_SAUDE = [
    "RDOR3.SA", "HAPV3.SA", "FLRY3.SA", "DASA3.SA", "RADL3.SA", 
    "ODPV3.SA", "HYPE3.SA", "QUAL3.SA", "MATD3.SA", "BLAU3.SA",
    "ONCO3.SA"
]

# ── energia elétrica e saneamento ─────────────────────────────────────
BR_ENERGIA_ELETRICA = [
    "ELET3.SA", "ELET6.SA", "CMIG3.SA", "CMIG4.SA", "CPFE3.SA", 
    "EQTL3.SA", "TAEE3.SA", "TAEE11.SA", "TRPL3.SA", "TRPL4.SA", 
    "CPLE3.SA", "CPLE6.SA", "SBSP3.SA", "AURE3.SA", "NEOE3.SA",
    "CSMG3.SA", "SAPR4.SA", "ENGI11.SA", "ALUP11.SA"
]

# ── logística e transporte ─────────────────────────────────────────────
BR_LOGISTICA = [
    "RAIL3.SA", "AZUL4.SA", "GOLL4.SA", "RENT3.SA", "CCRO3.SA", 
    "ECOR3.SA", "STBP3.SA", "JSLG3.SA", "HBSA3.SA"
]

# ── tecnologia ────────────────────────────────────────────────────────
BR_TECNOLOGIA = [
    "TOTS3.SA", "LWSA3.SA", "CASH3.SA", "IFCM3.SA", "MELI34.SA", 
    "POSI3.SA", "FIQE3.SA"
]

# ── imobiliário e construção civil ────────────────────────────────────
BR_IMOBILIARIO = [
    "MRVE3.SA", "CYRE3.SA", "EZTC3.SA", "DIRR3.SA", "TRIS3.SA", 
    "CURY3.SA", "LAVV3.SA", "EVEN3.SA", "MULT3.SA", "IGTI3.SA", 
    "IGTI11.SA", "ALOS3.SA", "TEND3.SA", "JHSF3.SA"
]

# ── papel e celulose ──────────────────────────────────────────────────
BR_PAPEL = [
    "SUZB3.SA", "KLBN3.SA", "KLBN4.SA", "KLBN11.SA", "RANI3.SA", 
    "DXCO3.SA"
]

# ── educação ──────────────────────────────────────────────────────────
BR_EDUCACAO = [
    "COGN3.SA", "YDUQ3.SA", "SEER3.SA", "CSED3.SA", "ANIM3.SA"
]

# ── telecomunicações ──────────────────────────────────────────────────
BR_TELECOM = [
    "VIVT3.SA", "TIMS3.SA", "OIBR3.SA", "OIBR4.SA", "DESK3.SA"
]

# ─────────────────────────────────────────────────────────────────────
# fiis — fundos de investimento imobiliário top 30
# ─────────────────────────────────────────────────────────────────────
BR_FIIS = [
    "HGLG11.SA", "BRCO11.SA", "LVBI11.SA", "XPLG11.SA", "VILG11.SA", # logística
    "XPML11.SA", "VISC11.SA", "HSML11.SA",                           # shoppings
    "PVBI11.SA", "RCRB11.SA", "HGRE11.SA", "VINO11.SA",              # lajes
    "CPTS11.SA", "RBRR11.SA", "KNCR11.SA", "IRDM11.SA", "RECR11.SA", # cris
    "DEVA11.SA", "PORD11.SA", "VGIR11.SA", "VRTA11.SA", "OUJP11.SA", "XPCI11.SA",
    "HFOF11.SA", "MXRF11.SA", "MGFF11.SA", "SNFF11.SA", "RBRX11.SA", # fofs
    "KNRI11.SA", "BBPO11.SA", "TRXF11.SA"                            # outros
]

# ─────────────────────────────────────────────────────────────────────
# índices e etfs b3
# ─────────────────────────────────────────────────────────────────────
BR_INDICES = [
    "^BVSP", "BOVA11.SA", "IVVB11.SA", "BRAX11.SA", "SMAL11.SA", 
    "DIVO11.SA", "FIND11.SA", "MATB11.SA", "ECOO11.SA", "GOVE11.SA", 
    "NASD11.SA", "HASH11.SA", "GOLD11.SA"
]

# ─────────────────────────────────────────────────────────────────────
# listas consolidadas
# ─────────────────────────────────────────────────────────────────────
BR_ACOES = list(dict.fromkeys(
    BR_ENERGIA + BR_MINERACAO + BR_BANCOS + BR_FINANCEIRO +
    BR_CONSUMO + BR_ALIMENTOS + BR_INDUSTRIA + BR_SAUDE +
    BR_ENERGIA_ELETRICA + BR_LOGISTICA + BR_TECNOLOGIA +
    BR_IMOBILIARIO + BR_PAPEL + BR_EDUCACAO + BR_TELECOM
))

BRASIL_TODOS = BR_ACOES + BR_FIIS

# screener b3 exclui fiis e etfs pois não possuem múltiplos como p/l e roe
SCREENER_B3 = list(dict.fromkeys(BR_ACOES))

# ─────────────────────────────────────────────────────────────────────
# funções de apoio e rótulos
# ─────────────────────────────────────────────────────────────────────
def get_opcoes_selectbox():
    """retorna lista formatada em minúsculas para st.selectbox com separadores."""
    opcoes = []

    def adicionar_bloco(titulo, lista_tickers):
        opcoes.append(f"─── {titulo} ───")
        for t in lista_tickers:
            nome_amigavel = t.replace('.SA', '').lower()
            opcoes.append(f"{t} — {nome_amigavel}")

    adicionar_bloco("⛽ energia & petróleo (br)", BR_ENERGIA)
    adicionar_bloco("⛏️ mineração & siderurgia (br)", BR_MINERACAO)
    adicionar_bloco("🏦 bancos (br)", BR_BANCOS)
    adicionar_bloco("🛡️ seguros, bolsa & financeiro (br)", BR_FINANCEIRO)
    adicionar_bloco("🛒 consumo & varejo (br)", BR_CONSUMO)
    adicionar_bloco("🍖 alimentos, bebidas & agro (br)", BR_ALIMENTOS)
    adicionar_bloco("🏭 indústria (br)", BR_INDUSTRIA)
    adicionar_bloco("🏥 saúde (br)", BR_SAUDE)
    adicionar_bloco("⚡ energia elétrica & saneamento (br)", BR_ENERGIA_ELETRICA)
    adicionar_bloco("🚀 logística & transporte (br)", BR_LOGISTICA)
    adicionar_bloco("💻 tecnologia (br)", BR_TECNOLOGIA)
    adicionar_bloco("🏗️ imobiliário & construção (br)", BR_IMOBILIARIO)
    adicionar_bloco("📄 papel & celulose (br)", BR_PAPEL)
    adicionar_bloco("🎓 educação (br)", BR_EDUCACAO)
    adicionar_bloco("📡 telecomunicações (br)", BR_TELECOM)
    adicionar_bloco("🏢 fiis (br)", BR_FIIS)
    adicionar_bloco("📊 etfs & índices (br)", BR_INDICES)

    # secções de RWA
    opcoes.append("─── 🌎 ondo finance (rwa) ───")
    for t in ONDO_TOKENS:
        opcoes.append(f"{t} — ondo asset")

    opcoes.append("─── 🔗 backed finance / xstocks (rwa) ───")
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
        "SLVon": "SLV",      # Silver Trust
    }
    
    if t in excecoes:
        return excecoes[t]

    # 2. Remover sufixos de emissoras (x para Backed, on para Ondo)
    if t.endswith('x') and len(t) > 1:
        return t[:-1]
    if t.lower().endswith('on') and len(t) > 2:
        return t[:-2]

    # 3. Remover prefixos de emissoras (b para bTokens/Backed)
    if t.startswith('b') and len(t) > 1:
        return t[1:]

    return t