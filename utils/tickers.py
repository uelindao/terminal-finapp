# =====================================================================
# XSTOCKS & MERCADO GLOBAL (MANTIDO INTACTO)
# =====================================================================
XSTOCKS_ACOES = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "NFLX",
    "COIN", "MSTR", "APP", "MA", "V", "JPM", "BAC", "WMT", "JNJ", "PG"
]

XSTOCKS_INDICES = [
    "SPY", "QQQ", "DIA", "IWM", "ARKK", "VT"
]

XSTOCKS_TODOS = XSTOCKS_ACOES + XSTOCKS_INDICES

XSTOCKS_LABELS = {
    "AAPL": "AAPL — Apple",
    "MSFT": "MSFT — Microsoft",
    "GOOGL": "GOOGL — Alphabet (Google)",
    "AMZN": "AMZN — Amazon",
    "META": "META — Meta (Facebook)",
    "TSLA": "TSLA — Tesla",
    "NVDA": "NVDA — NVIDIA",
    "NFLX": "NFLX — Netflix",
    "COIN": "COIN — Coinbase",
    "MSTR": "MSTR — MicroStrategy",
    "APP": "APP — AppLovin",
    "MA": "MA — Mastercard",
    "V": "V — Visa",
    "JPM": "JPM — JPMorgan Chase",
    "BAC": "BAC — Bank of America",
    "WMT": "WMT — Walmart",
    "JNJ": "JNJ — Johnson & Johnson",
    "PG": "PG — Procter & Gamble",
    "SPY": "SPY — S&P 500 ETF",
    "QQQ": "QQQ — Invesco QQQ (Nasdaq)",
    "DIA": "DIA — Dow Jones ETF",
    "IWM": "IWM — Russell 2000 ETF",
    "ARKK": "ARKK — ARK Innovation ETF",
    "VT": "VT — Vanguard Total World ETF"
}

SCREENER_US = XSTOCKS_ACOES


# ─────────────────────────────────────────────────────────────────────
# BRASIL — Organizado por setor (formato yfinance, sufixo .SA)
# ─────────────────────────────────────────────────────────────────────

# ── ENERGIA E PETRÓLEO ───────────────────────────────────────────────
BR_ENERGIA = [
    "PETR3.SA",   # Petrobras ON
    "PETR4.SA",   # Petrobras PN
    "PRIO3.SA",   # Prio (ex-PetroRio)
    "CSAN3.SA",   # Cosan
    "UGPA3.SA",   # Ultrapar
    "VBBR3.SA",   # Vibra Energia (ex-BR Distribuidora)
    "RECV3.SA",   # PetroRecôncavo
    "RRRP3.SA",   # 3R Petroleum
    "BRAV3.SA",   # Brava Energia
    "EGIE3.SA",   # Engie Brasil
]

# ── MINERAÇÃO E SIDERURGIA ───────────────────────────────────────────
BR_MINERACAO = [
    "VALE3.SA",   # Vale
    "GGBR3.SA",   # Gerdau ON
    "GGBR4.SA",   # Gerdau PN
    "GOAU3.SA",   # Metalúrgica Gerdau ON
    "GOAU4.SA",   # Metalúrgica Gerdau PN
    "CSNA3.SA",   # CSN
    "CMIN3.SA",   # CSN Mineração
    "USIM3.SA",   # Usiminas ON
    "USIM5.SA",   # Usiminas PNA
    "FESA4.SA",   # Ferbasa PN
]

# ── FINANCEIRO — BANCOS ───────────────────────────────────────────────
BR_BANCOS = [
    "ITUB3.SA",   # Itaú Unibanco ON
    "ITUB4.SA",   # Itaú Unibanco PN
    "ITSA3.SA",   # Itaúsa ON
    "ITSA4.SA",   # Itaúsa PN
    "BBAS3.SA",   # Banco do Brasil ON
    "BBDC3.SA",   # Bradesco ON
    "BBDC4.SA",   # Bradesco PN
    "SANB3.SA",   # Santander BR ON
    "SANB4.SA",   # Santander BR PN
    "SANB11.SA",  # Santander BR Units
    "BRSR3.SA",   # Banrisul ON
    "BRSR6.SA",   # Banrisul PNB
    "BPAC3.SA",   # BTG Pactual ON
    "BPAC11.SA",  # BTG Pactual Units
    "BMGB4.SA",   # BMG PN
]

# ── FINANCEIRO — SEGUROS E OUTROS ─────────────────────────────────────
BR_FINANCEIRO = [
    "BBSE3.SA",   # BB Seguridade
    "CXSE3.SA",   # Caixa Seguridade
    "SULA11.SA",  # SulAmérica Units
    "PSSA3.SA",   # Porto Seguro
    "WIZC3.SA",   # Wiz Co
    "XPBR31.SA",  # XP Inc BDR
]

# ── CONSUMO E VAREJO ──────────────────────────────────────────────────
BR_CONSUMO = [
    "MGLU3.SA",   # Magazine Luiza
    "LREN3.SA",   # Lojas Renner
    "AZZA3.SA",   # Azzas 2154 (ex-Arezzo)
    "SBFG3.SA",   # SBF Group (Centauro)
    "VIVA3.SA",   # Vivara
    "SOMA3.SA",   # Grupo Soma
    "NTCO3.SA",   # Natura & Co
    "ALPA3.SA",   # Alpargatas ON
    "ALPA4.SA",   # Alpargatas PN
    "AMAR3.SA",   # Marisa
    "GUAR3.SA",   # Guararapes
    "PETZ3.SA",   # Petz
    "SMFT3.SA",   # Smartfit
    "MOVI3.SA",   # Movida
]

# ── ALIMENTOS, BEBIDAS E AGRO ─────────────────────────────────────────
BR_ALIMENTOS = [
    "ABEV3.SA",   # Ambev
    "JBSS3.SA",   # JBS
    "BEEF3.SA",   # Minerva Foods
    "BRFS3.SA",   # BRF
    "MDIA3.SA",   # M. Dias Branco
    "CAML3.SA",   # Camil Alimentos
    "SLCE3.SA",   # SLC Agrícola
    "AGRO3.SA",   # Brasilagro
    "SMTO3.SA",   # São Martinho
    "TTEN3.SA",   # 3Tentos
    "CRAV3.SA",   # Cruzeiro do Sul Educacional (não agro, mas listado aqui)
]

# ── INDÚSTRIA E BENS DE CAPITAL ────────────────────────────────────────
BR_INDUSTRIA = [
    "WEGE3.SA",   # WEG
    "EMBR3.SA",   # Embraer
    "TUPY3.SA",   # Tupy
    "ROMI3.SA",   # Romi
    "POMO3.SA",   # Marcopolo ON
    "POMO4.SA",   # Marcopolo PN
    "INTB3.SA",   # Intelbras
    "KEPL3.SA",   # Kepler Weber
]

# ── SAÚDE ────────────────────────────────────────────────────────────
BR_SAUDE = [
    "RDOR3.SA",   # Rede D'Or
    "HAPV3.SA",   # Hapvida
    "FLRY3.SA",   # Fleury
    "DASA3.SA",   # Dasa
    "PARD3.SA",   # Pardini
    "RADL3.SA",   # Raia Drogasil
    "ODPV3.SA",   # Odontoprev
    "HYPE3.SA",   # Hypera Pharma
    "QUAL3.SA",   # Qualicorp
]

# ── ENERGIA ELÉTRICA E SANEAMENTO ─────────────────────────────────────
BR_ENERGIA_ELETRICA = [
    "ELET3.SA",   # Eletrobras ON
    "ELET6.SA",   # Eletrobras PNB
    "CMIG3.SA",   # CEMIG ON
    "CMIG4.SA",   # CEMIG PN
    "CPFE3.SA",   # CPFL Energia
    "EQTL3.SA",   # Equatorial
    "TAEE3.SA",   # Taesa ON
    "TAEE11.SA",  # Taesa Units
    "TRPL3.SA",   # Transmissão Paulista ON
    "TRPL4.SA",   # Transmissão Paulista PN
    "CPLE3.SA",   # Copel ON
    "CPLE6.SA",   # Copel PNB
    "SBSP3.SA",   # Sabesp
    "AURE3.SA",   # Auren Energia
    "ENBR3.SA",   # EDP Brasil
    "NEOE3.SA",   # Neoenergia
]

# ── LOGÍSTICA E TRANSPORTE ─────────────────────────────────────────────
BR_LOGISTICA = [
    "RAIL3.SA",   # Rumo Logística
    "TIMS3.SA",   # TIM Brasil
    "VIVT3.SA",   # Telefônica Vivo
    "AZUL4.SA",   # Azul Linhas Aéreas PN
    "GOLL4.SA",   # Gol Linhas Aéreas PN
    "RENT3.SA",   # Localiza
    "CCRO3.SA",   # CCR
    "ECOR3.SA",   # Ecorodovias
]

# ── TECNOLOGIA ────────────────────────────────────────────────────────
BR_TECNOLOGIA = [
    "TOTS3.SA",   # TOTVS
    "LWSA3.SA",   # Locaweb
    "CASH3.SA",   # Méliuz
    "IFCM3.SA",   # Infracommerce
    "MELI34.SA",  # MercadoLivre BDR
    "POSI3.SA",   # Positivo Tecnologia
]

# ── IMOBILIÁRIO E CONSTRUÇÃO CIVIL ────────────────────────────────────
BR_IMOBILIARIO = [
    "MRVE3.SA",   # MRV Engenharia
    "CYRE3.SA",   # Cyrela
    "EZTC3.SA",   # EZTEC
    "DIRR3.SA",   # Direcional
    "TRIS3.SA",   # Trisul
    "CURY3.SA",   # Cury Construtora
    "LAVV3.SA",   # Lavvi
    "EVEN3.SA",   # Even
    "MULT3.SA",   # Multiplan
    "IGTI3.SA",   # Iguatemi ON
    "IGTI11.SA",  # Iguatemi Units
]

# ── PAPEL E CELULOSE ──────────────────────────────────────────────────
BR_PAPEL = [
    "SUZB3.SA",   # Suzano
    "KLBN3.SA",   # Klabin ON
    "KLBN4.SA",   # Klabin PN
    "KLBN11.SA",  # Klabin Units
]

# ── EDUCAÇÃO ──────────────────────────────────────────────────────────
BR_EDUCACAO = [
    "COGN3.SA",   # Cogna
    "YDUQ3.SA",   # Yduqs
    "SEER3.SA",   # Ser Educacional
]

# ── TELECOMUNICAÇÕES ──────────────────────────────────────────────────
BR_TELECOM = [
    "VIVT3.SA",   # Telefônica Vivo (também em Logística — remover duplicata)
    "TIMS3.SA",   # TIM (também em Logística — remover duplicata)
    "OIBR3.SA",   # Oi ON
]

# ─────────────────────────────────────────────────────────────────────
# FIIs — Fundos de Investimento Imobiliário Top 30
# ─────────────────────────────────────────────────────────────────────
BR_FIIS = [
    # Logística
    "HGLG11.SA",  # CSHG Logística
    "BRCO11.SA",  # Bresco Logística
    "LVBI11.SA",  # VBI Logístico
    "XPLG11.SA",  # XP Log
    "VILG11.SA",  # Vinci Logística
    # Shoppings
    "XPML11.SA",  # XP Malls
    "VISC11.SA",  # Vinci Shopping Centers
    "HSML11.SA",  # HSI Malls
    "IGTI11.SA",  # Iguatemi (duplicata com ações — manter por ser FII de referência)
    # Lajes Corporativas
    "PVBI11.SA",  # VBI Prime Properties
    "RCRB11.SA",  # Rio Bravo Renda Corp
    "HGRE11.SA",  # CSHG Real Estate
    "VINO11.SA",  # Vinci Offices
    # CRIs e Recebíveis
    "CPTS11.SA",  # Capitânia Securities
    "RBRR11.SA",  # RBR Rendimento High Grade
    "KNCR11.SA",  # Kinea Rendimentos CRI
    "IRDM11.SA",  # Iridium Recebíveis CRI
    "RECR11.SA",  # REC Recebíveis
    "DEVA11.SA",  # Devant Recebíveis
    "PORD11.SA",  # Polo Recebíveis
    "VGIR11.SA",  # Valora CRI
    "VRTA11.SA",  # Fator Verita
    "OUJP11.SA",  # Ourinvest JPP CRI
    "XPCI11.SA",  # XP Crédito Imobiliário
    # FOFs e Diversificados
    "HFOF11.SA",  # Hedge FOF
    "MXRF11.SA",  # Maxi Renda
    "MGFF11.SA",  # Mogno FOF
    "SNFF11.SA",  # Suno FOF
    "RBRX11.SA",  # RBR Alpha Multiestrategia
    # Outros
    "KNRI11.SA",  # Kinea Renda Imobiliária
    "BBPO11.SA",  # BB Progressivo II
    "TRXF11.SA",  # TRX Real Estate
]

# ─────────────────────────────────────────────────────────────────────
# ÍNDICES E ETFs B3
# ─────────────────────────────────────────────────────────────────────
BR_INDICES = [
    "^BVSP",      # Ibovespa (índice — não usa .SA)
    "BOVA11.SA",  # ETF Ibovespa
    "IVVB11.SA",  # ETF S&P 500 em BRL (popular entre BR investors)
    "BRAX11.SA",  # ETF IBRX-100
    "SMAL11.SA",  # ETF Small Caps
    "DIVO11.SA",  # ETF Dividendos
    "FIND11.SA",  # ETF Setor Financeiro
    "MATB11.SA",  # ETF Materiais Básicos
    "ECOO11.SA",  # ETF Sustentabilidade
    "GOVE11.SA",  # ETF Governança Corporativa
    "NASD11.SA",  # ETF Nasdaq em BRL
    "HASH11.SA",  # ETF Criptoativos
    "GOLD11.SA",  # ETF Ouro
]

# ─────────────────────────────────────────────────────────────────────
# LISTAS CONSOLIDADAS
# ─────────────────────────────────────────────────────────────────────

# Todas as ações (sem FIIs e sem índices)
BR_ACOES = list(dict.fromkeys(
    BR_ENERGIA + BR_MINERACAO + BR_BANCOS + BR_FINANCEIRO +
    BR_CONSUMO + BR_ALIMENTOS + BR_INDUSTRIA + BR_SAUDE +
    BR_ENERGIA_ELETRICA + BR_LOGISTICA + BR_TECNOLOGIA +
    BR_IMOBILIARIO + BR_PAPEL + BR_EDUCACAO + BR_TELECOM
))

# Todos os ativos BR em lista plana (watchlist inicial)
BRASIL_TODOS = BR_ACOES + BR_FIIS

# ─────────────────────────────────────────────────────────────────────
# RÓTULOS PARA EXIBIÇÃO NOS SELECTBOXES
# ─────────────────────────────────────────────────────────────────────
BRASIL_LABELS = {
    # ENERGIA
    "PETR3.SA":  "PETR3.SA — Petrobras ON",
    "PETR4.SA":  "PETR4.SA — Petrobras PN",
    "PRIO3.SA":  "PRIO3.SA — Prio Energia",
    "CSAN3.SA":  "CSAN3.SA — Cosan",
    "UGPA3.SA":  "UGPA3.SA — Ultrapar",
    "VBBR3.SA":  "VBBR3.SA — Vibra Energia",
    "RECV3.SA":  "RECV3.SA — PetroRecôncavo",
    "RRRP3.SA":  "RRRP3.SA — 3R Petroleum",
    "BRAV3.SA":  "BRAV3.SA — Brava Energia",
    "EGIE3.SA":  "EGIE3.SA — Engie Brasil",
    # MINERAÇÃO
    "VALE3.SA":  "VALE3.SA — Vale",
    "GGBR3.SA":  "GGBR3.SA — Gerdau ON",
    "GGBR4.SA":  "GGBR4.SA — Gerdau PN",
    "GOAU3.SA":  "GOAU3.SA — Metalúrgica Gerdau ON",
    "GOAU4.SA":  "GOAU4.SA — Metalúrgica Gerdau PN",
    "CSNA3.SA":  "CSNA3.SA — CSN",
    "CMIN3.SA":  "CMIN3.SA — CSN Mineração",
    "USIM3.SA":  "USIM3.SA — Usiminas ON",
    "USIM5.SA":  "USIM5.SA — Usiminas PNA",
    "FESA4.SA":  "FESA4.SA — Ferbasa PN",
    # BANCOS
    "ITUB3.SA":  "ITUB3.SA — Itaú Unibanco ON",
    "ITUB4.SA":  "ITUB4.SA — Itaú Unibanco PN",
    "ITSA3.SA":  "ITSA3.SA — Itaúsa ON",
    "ITSA4.SA":  "ITSA4.SA — Itaúsa PN",
    "BBAS3.SA":  "BBAS3.SA — Banco do Brasil",
    "BBDC3.SA":  "BBDC3.SA — Bradesco ON",
    "BBDC4.SA":  "BBDC4.SA — Bradesco PN",
    "SANB3.SA":  "SANB3.SA — Santander BR ON",
    "SANB4.SA":  "SANB4.SA — Santander BR PN",
    "SANB11.SA": "SANB11.SA — Santander BR Units",
    "BRSR3.SA":  "BRSR3.SA — Banrisul ON",
    "BRSR6.SA":  "BRSR6.SA — Banrisul PNB",
    "BPAC3.SA":  "BPAC3.SA — BTG Pactual ON",
    "BPAC11.SA": "BPAC11.SA — BTG Pactual Units",
    "BMGB4.SA":  "BMGB4.SA — BMG PN",
    # FINANCEIRO
    "BBSE3.SA":  "BBSE3.SA — BB Seguridade",
    "CXSE3.SA":  "CXSE3.SA — Caixa Seguridade",
    "SULA11.SA": "SULA11.SA — SulAmérica Units",
    "PSSA3.SA":  "PSSA3.SA — Porto Seguro",
    "WIZC3.SA":  "WIZC3.SA — Wiz Co",
    "XPBR31.SA": "XPBR31.SA — XP Inc BDR",
    # CONSUMO
    "MGLU3.SA":  "MGLU3.SA — Magazine Luiza",
    "LREN3.SA":  "LREN3.SA — Lojas Renner",
    "AZZA3.SA":  "AZZA3.SA — Azzas 2154",
    "SBFG3.SA":  "SBFG3.SA — SBF Group (Centauro)",
    "VIVA3.SA":  "VIVA3.SA — Vivara",
    "SOMA3.SA":  "SOMA3.SA — Grupo Soma",
    "NTCO3.SA":  "NTCO3.SA — Natura & Co",
    "ALPA3.SA":  "ALPA3.SA — Alpargatas ON",
    "ALPA4.SA":  "ALPA4.SA — Alpargatas PN",
    "AMAR3.SA":  "AMAR3.SA — Marisa",
    "GUAR3.SA":  "GUAR3.SA — Guararapes",
    "PETZ3.SA":  "PETZ3.SA — Petz",
    "SMFT3.SA":  "SMFT3.SA — Smartfit",
    "MOVI3.SA":  "MOVI3.SA — Movida",
    # ALIMENTOS
    "ABEV3.SA":  "ABEV3.SA — Ambev",
    "JBSS3.SA":  "JBSS3.SA — JBS",
    "BEEF3.SA":  "BEEF3.SA — Minerva Foods",
    "BRFS3.SA":  "BRFS3.SA — BRF",
    "MDIA3.SA":  "MDIA3.SA — M. Dias Branco",
    "CAML3.SA":  "CAML3.SA — Camil Alimentos",
    "SLCE3.SA":  "SLCE3.SA — SLC Agrícola",
    "AGRO3.SA":  "AGRO3.SA — Brasilagro",
    "SMTO3.SA":  "SMTO3.SA — São Martinho",
    "TTEN3.SA":  "TTEN3.SA — 3Tentos",
    # INDÚSTRIA
    "WEGE3.SA":  "WEGE3.SA — WEG",
    "EMBR3.SA":  "EMBR3.SA — Embraer",
    "TUPY3.SA":  "TUPY3.SA — Tupy",
    "ROMI3.SA":  "ROMI3.SA — Romi",
    "POMO3.SA":  "POMO3.SA — Marcopolo ON",
    "POMO4.SA":  "POMO4.SA — Marcopolo PN",
    "INTB3.SA":  "INTB3.SA — Intelbras",
    "KEPL3.SA":  "KEPL3.SA — Kepler Weber",
    # SAÚDE
    "RDOR3.SA":  "RDOR3.SA — Rede D'Or",
    "HAPV3.SA":  "HAPV3.SA — Hapvida",
    "FLRY3.SA":  "FLRY3.SA — Fleury",
    "DASA3.SA":  "DASA3.SA — Dasa",
    "PARD3.SA":  "PARD3.SA — Pardini",
    "RADL3.SA":  "RADL3.SA — Raia Drogasil",
    "ODPV3.SA":  "ODPV3.SA — Odontoprev",
    "HYPE3.SA":  "HYPE3.SA — Hypera Pharma",
    "QUAL3.SA":  "QUAL3.SA — Qualicorp",
    # ENERGIA ELÉTRICA
    "ELET3.SA":  "ELET3.SA — Eletrobras ON",
    "ELET6.SA":  "ELET6.SA — Eletrobras PNB",
    "CMIG3.SA":  "CMIG3.SA — CEMIG ON",
    "CMIG4.SA":  "CMIG4.SA — CEMIG PN",
    "CPFE3.SA":  "CPFE3.SA — CPFL Energia",
    "EQTL3.SA":  "EQTL3.SA — Equatorial",
    "TAEE3.SA":  "TAEE3.SA — Taesa ON",
    "TAEE11.SA": "TAEE11.SA — Taesa Units",
    "TRPL3.SA":  "TRPL3.SA — Transmissão Paulista ON",
    "TRPL4.SA":  "TRPL4.SA — Transmissão Paulista PN",
    "CPLE3.SA":  "CPLE3.SA — Copel ON",
    "CPLE6.SA":  "CPLE6.SA — Copel PNB",
    "SBSP3.SA":  "SBSP3.SA — Sabesp",
    "AURE3.SA":  "AURE3.SA — Auren Energia",
    "ENBR3.SA":  "ENBR3.SA — EDP Brasil",
    "NEOE3.SA":  "NEOE3.SA — Neoenergia",
    # LOGÍSTICA
    "RAIL3.SA":  "RAIL3.SA — Rumo Logística",
    "AZUL4.SA":  "AZUL4.SA — Azul PN",
    "GOLL4.SA":  "GOLL4.SA — Gol PN",
    "RENT3.SA":  "RENT3.SA — Localiza",
    "CCRO3.SA":  "CCRO3.SA — CCR",
    "ECOR3.SA":  "ECOR3.SA — Ecorodovias",
    "TIMS3.SA":  "TIMS3.SA — TIM Brasil",
    "VIVT3.SA":  "VIVT3.SA — Telefônica Vivo",
    # TECNOLOGIA
    "TOTS3.SA":  "TOTS3.SA — TOTVS",
    "LWSA3.SA":  "LWSA3.SA — Locaweb",
    "CASH3.SA":  "CASH3.SA — Méliuz",
    "IFCM3.SA":  "IFCM3.SA — Infracommerce",
    "MELI34.SA": "MELI34.SA — MercadoLivre BDR",
    "POSI3.SA":  "POSI3.SA — Positivo Tecnologia",
    # IMOBILIÁRIO
    "MRVE3.SA":  "MRVE3.SA — MRV Engenharia",
    "CYRE3.SA":  "CYRE3.SA — Cyrela",
    "EZTC3.SA":  "EZTC3.SA — EZTEC",
    "DIRR3.SA":  "DIRR3.SA — Direcional",
    "TRIS3.SA":  "TRIS3.SA — Trisul",
    "CURY3.SA":  "CURY3.SA — Cury Construtora",
    "LAVV3.SA":  "LAVV3.SA — Lavvi",
    "EVEN3.SA":  "EVEN3.SA — Even",
    "MULT3.SA":  "MULT3.SA — Multiplan",
    "IGTI3.SA":  "IGTI3.SA — Iguatemi ON",
    "IGTI11.SA": "IGTI11.SA — Iguatemi Units",
    # PAPEL E CELULOSE
    "SUZB3.SA":  "SUZB3.SA — Suzano",
    "KLBN3.SA":  "KLBN3.SA — Klabin ON",
    "KLBN4.SA":  "KLBN4.SA — Klabin PN",
    "KLBN11.SA": "KLBN11.SA — Klabin Units",
    # EDUCAÇÃO
    "COGN3.SA":  "COGN3.SA — Cogna",
    "YDUQ3.SA":  "YDUQ3.SA — Yduqs",
    "SEER3.SA":  "SEER3.SA — Ser Educacional",
    # FIIs
    "HGLG11.SA": "HGLG11.SA — CSHG Logística (FII)",
    "BRCO11.SA": "BRCO11.SA — Bresco Logística (FII)",
    "LVBI11.SA": "LVBI11.SA — VBI Logístico (FII)",
    "XPLG11.SA": "XPLG11.SA — XP Log (FII)",
    "VILG11.SA": "VILG11.SA — Vinci Logística (FII)",
    "XPML11.SA": "XPML11.SA — XP Malls (FII)",
    "VISC11.SA": "VISC11.SA — Vinci Shopping Centers (FII)",
    "HSML11.SA": "HSML11.SA — HSI Malls (FII)",
    "PVBI11.SA": "PVBI11.SA — VBI Prime Properties (FII)",
    "RCRB11.SA": "RCRB11.SA — Rio Bravo Renda Corp (FII)",
    "HGRE11.SA": "HGRE11.SA — CSHG Real Estate (FII)",
    "VINO11.SA": "VINO11.SA — Vinci Offices (FII)",
    "CPTS11.SA": "CPTS11.SA — Capitânia Securities (FII)",
    "RBRR11.SA": "RBRR11.SA — RBR High Grade (FII)",
    "KNCR11.SA": "KNCR11.SA — Kinea Rendimentos CRI (FII)",
    "IRDM11.SA": "IRDM11.SA — Iridium Recebíveis (FII)",
    "RECR11.SA": "RECR11.SA — REC Recebíveis (FII)",
    "DEVA11.SA": "DEVA11.SA — Devant Recebíveis (FII)",
    "PORD11.SA": "PORD11.SA — Polo Recebíveis (FII)",
    "VGIR11.SA": "VGIR11.SA — Valora CRI (FII)",
    "VRTA11.SA": "VRTA11.SA — Fator Verita (FII)",
    "OUJP11.SA": "OUJP11.SA — Ourinvest JPP CRI (FII)",
    "XPCI11.SA": "XPCI11.SA — XP Crédito Imobiliário (FII)",
    "HFOF11.SA": "HFOF11.SA — Hedge FOF (FII)",
    "MXRF11.SA": "MXRF11.SA — Maxi Renda (FII)",
    "MGFF11.SA": "MGFF11.SA — Mogno FOF (FII)",
    "SNFF11.SA": "SNFF11.SA — Suno FOF (FII)",
    "RBRX11.SA": "RBRX11.SA — RBR Alpha (FII)",
    "KNRI11.SA": "KNRI11.SA — Kinea Renda Imobiliária (FII)",
    "BBPO11.SA": "BBPO11.SA — BB Progressivo II (FII)",
    "TRXF11.SA": "TRXF11.SA — TRX Real Estate (FII)",
    # ÍNDICES E ETFs
    "^BVSP":     "^BVSP — Ibovespa",
    "BOVA11.SA": "BOVA11.SA — ETF Ibovespa",
    "IVVB11.SA": "IVVB11.SA — ETF S&P 500 (BRL)",
    "BRAX11.SA": "BRAX11.SA — ETF IBRX-100",
    "SMAL11.SA": "SMAL11.SA — ETF Small Caps",
    "DIVO11.SA": "DIVO11.SA — ETF Dividendos",
    "FIND11.SA": "FIND11.SA — ETF Financeiro",
    "MATB11.SA": "MATB11.SA — ETF Materiais Básicos",
    "ECOO11.SA": "ECOO11.SA — ETF Sustentabilidade",
    "GOVE11.SA": "GOVE11.SA — ETF Governança Corp.",
    "NASD11.SA": "NASD11.SA — ETF Nasdaq (BRL)",
    "HASH11.SA": "HASH11.SA — ETF Criptoativos",
    "GOLD11.SA": "GOLD11.SA — ETF Ouro",
}

# ─────────────────────────────────────────────────────────────────────
# SCREENER B3
# ─────────────────────────────────────────────────────────────────────
# Screener B3: ações com fundamentals disponíveis no yfinance
# FIIs e ETFs excluídos pois não têm P/L, ROE etc.
SCREENER_B3 = list(dict.fromkeys(BR_ACOES + [
    # Adicionais relevantes não incluídos nas listas acima
    "ABEV3.SA", "WEGE3.SA", "RENT3.SA", "PRIO3.SA", "GGBR4.SA",
    "RADL3.SA", "SUZB3.SA", "LREN3.SA", "MGLU3.SA", "EMBR3.SA",
    "CPLE6.SA", "TAEE11.SA", "EQTL3.SA", "JBSS3.SA", "BRFS3.SA",
    "SBSP3.SA", "VIVT3.SA", "CMIG4.SA", "KLBN11.SA", "CCRO3.SA",
]))


# ─────────────────────────────────────────────────────────────────────
# FUNÇÕES DE APOIO
# ─────────────────────────────────────────────────────────────────────
def get_opcoes_selectbox():
    """
    Retorna lista formatada para st.selectbox com separadores por grupo.
    Cobre: Ações BR por setor, FIIs, ETFs BR, XStocks, ETFs globais.
    """
    opcoes = []

    opcoes.append("─── ⛽ ENERGIA & PETRÓLEO (BR) ───")
    for t in BR_ENERGIA:
        opcoes.append(BRASIL_LABELS.get(t, t))

    opcoes.append("─── ⛏️ MINERAÇÃO & SIDERURGIA (BR) ───")
    for t in BR_MINERACAO:
        opcoes.append(BRASIL_LABELS.get(t, t))

    opcoes.append("─── 🏦 BANCOS (BR) ───")
    for t in BR_BANCOS:
        opcoes.append(BRASIL_LABELS.get(t, t))

    opcoes.append("─── 🛡️ SEGUROS & FINANCEIRO (BR) ───")
    for t in BR_FINANCEIRO:
        opcoes.append(BRASIL_LABELS.get(t, t))

    opcoes.append("─── 🛒 CONSUMO & VAREJO (BR) ───")
    for t in BR_CONSUMO:
        opcoes.append(BRASIL_LABELS.get(t, t))

    opcoes.append("─── 🍖 ALIMENTOS, BEBIDAS & AGRO (BR) ───")
    for t in BR_ALIMENTOS:
        opcoes.append(BRASIL_LABELS.get(t, t))

    opcoes.append("─── 🏭 INDÚSTRIA (BR) ───")
    for t in BR_INDUSTRIA:
        opcoes.append(BRASIL_LABELS.get(t, t))

    opcoes.append("─── 🏥 SAÚDE (BR) ───")
    for t in BR_SAUDE:
        opcoes.append(BRASIL_LABELS.get(t, t))

    opcoes.append("─── ⚡ ENERGIA ELÉTRICA & SANEAMENTO (BR) ───")
    for t in BR_ENERGIA_ELETRICA:
        opcoes.append(BRASIL_LABELS.get(t, t))

    opcoes.append("─── 🚀 LOGÍSTICA & TRANSPORTE (BR) ───")
    for t in BR_LOGISTICA:
        opcoes.append(BRASIL_LABELS.get(t, t))

    opcoes.append("─── 💻 TECNOLOGIA (BR) ───")
    for t in BR_TECNOLOGIA:
        opcoes.append(BRASIL_LABELS.get(t, t))

    opcoes.append("─── 🏗️ IMOBILIÁRIO & CONSTRUÇÃO (BR) ───")
    for t in BR_IMOBILIARIO:
        opcoes.append(BRASIL_LABELS.get(t, t))

    opcoes.append("─── 📄 PAPEL & CELULOSE (BR) ───")
    for t in BR_PAPEL:
        opcoes.append(BRASIL_LABELS.get(t, t))

    opcoes.append("─── 🎓 EDUCAÇÃO (BR) ───")
    for t in BR_EDUCACAO:
        opcoes.append(BRASIL_LABELS.get(t, t))

    opcoes.append("─── 🏢 FIIs (BR) ───")
    for t in BR_FIIS:
        opcoes.append(BRASIL_LABELS.get(t, t))

    opcoes.append("─── 📊 ETFs & ÍNDICES (BR) ───")
    for t in BR_INDICES:
        opcoes.append(BRASIL_LABELS.get(t, t))

    opcoes.append("─── 🌎 XSTOCKS RWA (NYSE/NASDAQ) ───")
    for t in XSTOCKS_ACOES:
        opcoes.append(XSTOCKS_LABELS.get(t, t))

    opcoes.append("─── 📈 ETFs GLOBAIS ───")
    for t in XSTOCKS_INDICES:
        opcoes.append(XSTOCKS_LABELS.get(t, t))

    opcoes.append("── ✏️ OUTRO (digitar manualmente) ──")
    return opcoes


def ticker_from_label(label: str) -> str:
    """Extrai o ticker limpo da string do selectbox (ex: 'PETR4.SA — Petrobras PN' vira 'PETR4.SA')."""
    if not label or label.startswith("─") or label.startswith("✏️"):
        return ""
    return label.split(" — ")[0].strip()