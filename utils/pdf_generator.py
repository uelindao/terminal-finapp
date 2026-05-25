"""
utils/pdf_generator.py
Gerador de teses de investimento em PDF.
Usa ReportLab para formatação profissional.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer,
    Table, TableStyle, HRFlowable,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from io import BytesIO
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Paleta de cores do FinTerminal ────────────────────────────────────────────
COR_PRIMARIA   = colors.HexColor("#FF9900")
COR_FUNDO      = colors.HexColor("#0d0d0d")
COR_TEXTO      = colors.HexColor("#C0C0C0")
COR_SECUNDARIA = colors.HexColor("#333333")
COR_VERDE      = colors.HexColor("#00C853")
COR_VERMELHO   = colors.HexColor("#FF1744")
BRANCO         = colors.white
PRETO          = colors.black


def gerar_tese_pdf(
    ticker:        str,
    nome:          str,
    setor:         str,
    health_score:  int,
    preco_atual:   float,
    fundamentos:   dict,
    analise_ia:    str,
    alertas:       list,
    breakdown:     dict,
    macro_context: dict,
) -> bytes:
    """
    Gera um PDF profissional com a tese de investimento.
    Retorna bytes para download direto no Streamlit.
    """
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize     = A4,
        rightMargin  = 2 * cm,
        leftMargin   = 2 * cm,
        topMargin    = 2.5 * cm,
        bottomMargin = 2 * cm,
    )

    styles = getSampleStyleSheet()

    # ── Estilos customizados ─────────────────────────────────────────────────

    st_titulo = ParagraphStyle(
        "titulo",
        parent     = styles["Normal"],
        fontSize   = 20,
        textColor  = COR_PRIMARIA,
        fontName   = "Courier-Bold",
        spaceAfter = 4,
    )
    st_subtitulo = ParagraphStyle(
        "subtitulo",
        parent     = styles["Normal"],
        fontSize   = 11,
        textColor  = colors.HexColor("#888888"),
        fontName   = "Courier",
        spaceAfter = 2,
    )
    st_secao = ParagraphStyle(
        "secao",
        parent      = styles["Normal"],
        fontSize    = 10,
        textColor   = COR_PRIMARIA,
        fontName    = "Courier-Bold",
        spaceBefore = 14,
        spaceAfter  = 4,
        borderPad   = 4,
    )
    st_corpo = ParagraphStyle(
        "corpo",
        parent     = styles["Normal"],
        fontSize   = 9,
        textColor  = colors.HexColor("#444444"),
        fontName   = "Courier",
        leading    = 14,
        spaceAfter = 3,
    )
    st_alerta = ParagraphStyle(
        "alerta",
        parent     = styles["Normal"],
        fontSize   = 8.5,
        textColor  = colors.HexColor("#333333"),
        fontName   = "Courier",
        leading    = 13,
        leftIndent = 8,
    )
    st_disclaimer = ParagraphStyle(
        "disclaimer",
        parent    = styles["Normal"],
        fontSize  = 7.5,
        textColor = colors.HexColor("#888888"),
        fontName  = "Courier",
        leading   = 11,
        alignment = TA_CENTER,
    )

    conteudo = []

    # ── Cabeçalho ────────────────────────────────────────────────────────────

    conteudo.append(Paragraph("FINTERMINAL", st_titulo))
    conteudo.append(Paragraph(
        f"tese de investimento — {ticker.upper()}",
        st_subtitulo,
    ))
    conteudo.append(Paragraph(
        f"gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} "
        f"| deepseek v4 pro",
        st_subtitulo,
    ))
    conteudo.append(HRFlowable(
        width="100%", thickness=1,
        color=COR_PRIMARIA, spaceAfter=12,
    ))

    # ── Sumário do ativo ─────────────────────────────────────────────────────

    cor_score = (
        COR_VERDE    if health_score >= 65 else
        COR_PRIMARIA if health_score >= 40 else
        COR_VERMELHO
    )
    status_txt = (
        "acumulacao" if health_score >= 65 else
        "manutencao" if health_score >= 40 else
        "reduzir"
    )

    dados_header = [
        ["ATIVO",           "EMPRESA",         "SETOR",           "PRECO"],
        [ticker.upper(),    nome[:25],          setor[:25],        f"R$ {preco_atual:,.2f}"],
        ["HEALTH SCORE",    "STATUS",           "SELIC",           "VIX"],
        [
            f"{health_score}/100",
            status_txt.upper(),
            f"{macro_context.get('selic', 10.75):.2f}%",
            f"{macro_context.get('vix', 15.0):.1f}",
        ],
    ]

    tabela_header = Table(
        dados_header,
        colWidths=[4 * cm, 5 * cm, 4.5 * cm, 3.5 * cm],
    )
    tabela_header.setStyle(TableStyle([
        # Linha de labels (0)
        ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#1a1a1a")),
        ("TEXTCOLOR",     (0, 0), (-1, 0), COR_PRIMARIA),
        ("FONTNAME",      (0, 0), (-1, 0), "Courier-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 8),
        # Linha de valores (1)
        ("BACKGROUND",    (0, 1), (-1, 1), colors.HexColor("#f8f8f8")),
        ("TEXTCOLOR",     (0, 1), (-1, 1), PRETO),
        ("FONTNAME",      (0, 1), (-1, 1), "Courier-Bold"),
        ("FONTSIZE",      (0, 1), (-1, 1), 9),
        # Segunda linha de labels (2)
        ("BACKGROUND",    (0, 2), (-1, 2), colors.HexColor("#1a1a1a")),
        ("TEXTCOLOR",     (0, 2), (-1, 2), COR_PRIMARIA),
        ("FONTNAME",      (0, 2), (-1, 2), "Courier-Bold"),
        ("FONTSIZE",      (0, 2), (-1, 2), 8),
        # Segunda linha de valores (3)
        ("BACKGROUND",    (0, 3), (0, 3), colors.HexColor("#fff3e0")),
        ("TEXTCOLOR",     (0, 3), (0, 3), cor_score),
        ("FONTNAME",      (0, 3), (0, 3), "Courier-Bold"),
        ("FONTSIZE",      (0, 3), (-1, 3), 9),
        ("BACKGROUND",    (1, 3), (-1, 3), colors.HexColor("#f8f8f8")),
        ("TEXTCOLOR",     (1, 3), (-1, 3), PRETO),
        # Bordas gerais
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    conteudo.append(tabela_header)
    conteudo.append(Spacer(1, 0.3 * cm))

    # ── Fundamentos ──────────────────────────────────────────────────────────

    conteudo.append(Paragraph("FUNDAMENTOS", st_secao))

    fund = fundamentos or {}

    def _fmt(val, suffix=""):
        """Formata valor com fallback n/d."""
        if val is None or val == "n/d" or val == "":
            return "n/d"
        try:
            return f"{float(val):.2f}{suffix}"
        except (TypeError, ValueError):
            return str(val)

    dados_fund = [
        ["P/L",                 "P/VP",                  "ROE",
         "DY",                  "MARGEM",                "EV/EBITDA"],
        [
            _fmt(fund.get("p/l")),
            _fmt(fund.get("p/vp")),
            _fmt(fund.get("roe%"), "%"),
            _fmt(fund.get("dy%"), "%"),
            _fmt(fund.get("margem%"), "%"),
            _fmt(fund.get("ev/ebitda")),
        ],
    ]

    tabela_fund = Table(dados_fund, colWidths=[2.8 * cm] * 6)
    tabela_fund.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#f5f5f5")),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.HexColor("#666666")),
        ("FONTNAME",      (0, 0), (-1, 0), "Courier-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8.5),
        ("FONTNAME",      (0, 1), (-1, 1), "Courier-Bold"),
        ("TEXTCOLOR",     (0, 1), (-1, 1), PRETO),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    conteudo.append(tabela_fund)

    # ── Análise IA ───────────────────────────────────────────────────────────

    conteudo.append(Paragraph("ANALISE — DEEPSEEK V4 PRO", st_secao))

    for linha in (analise_ia or "análise não disponível.").split("\n"):
        linha = linha.strip()
        if not linha:
            conteudo.append(Spacer(1, 0.15 * cm))
            continue
        # Escapa caracteres especiais do ReportLab
        linha = (linha
                 .replace("&", "&amp;")
                 .replace("<", "&lt;")
                 .replace(">", "&gt;"))
        conteudo.append(Paragraph(linha, st_corpo))

    # ── Alertas do motor quantitativo ────────────────────────────────────────

    if alertas:
        conteudo.append(Paragraph("ALERTAS DO MOTOR QUANTITATIVO", st_secao))
        for alerta in alertas[:10]:
            alerta_esc = (str(alerta)
                          .replace("&", "&amp;")
                          .replace("<", "&lt;")
                          .replace(">", "&gt;"))
            conteudo.append(Paragraph(f"• {alerta_esc}", st_alerta))

    # ── Breakdown do health score ─────────────────────────────────────────────

    if breakdown:
        conteudo.append(Paragraph("BREAKDOWN DO HEALTH SCORE", st_secao))

        dados_bd = [["COMPONENTE", "PONTUACAO"]]
        for k, v in list(breakdown.items())[:12]:
            k_esc = (str(k)
                     .replace("&", "&amp;")
                     .replace("<", "&lt;")
                     .replace(">", "&gt;"))
            dados_bd.append([k_esc, str(v)])

        tabela_bd = Table(dados_bd, colWidths=[12 * cm, 5 * cm])
        tabela_bd.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#f5f5f5")),
            ("TEXTCOLOR",     (0, 0), (-1, 0), colors.HexColor("#666666")),
            ("FONTNAME",      (0, 0), (-1, 0), "Courier-Bold"),
            ("FONTNAME",      (0, 1), (-1, -1), "Courier"),
            ("FONTSIZE",      (0, 0), (-1, -1), 8),
            ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#eeeeee")),
            ("ALIGN",         (1, 0), (1, -1), "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#fafafa")]),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        conteudo.append(tabela_bd)

    # ── Disclaimer ───────────────────────────────────────────────────────────

    conteudo.append(Spacer(1, 0.5 * cm))
    conteudo.append(HRFlowable(
        width="100%", thickness=0.5,
        color=colors.HexColor("#cccccc"),
    ))
    conteudo.append(Spacer(1, 0.2 * cm))
    conteudo.append(Paragraph(
        "este documento foi gerado automaticamente pelo finterminal "
        "com auxilio de inteligencia artificial (deepseek v4 pro). "
        "nao constitui recomendacao de investimento. "
        "as informacoes tem carater exclusivamente informativo e educacional. "
        "consulte um profissional habilitado antes de tomar decisoes de investimento.",
        st_disclaimer,
    ))

    try:
        doc.build(conteudo)
    except Exception as e:
        logger.error(f"[pdf_generator] erro ao montar PDF para {ticker}: {e}")
        raise

    buffer.seek(0)
    return buffer.read()
