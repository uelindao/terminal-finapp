"""Testes de utils/fii_scraper — parser da listagem de FIIs do Fundamentus."""
from utils.fii_scraper import parsear_tabela_fiis, _br_num


def test_br_num():
    assert _br_num("165.857.000") == 165857000.0
    assert _br_num("6,90") == 6.9
    assert _br_num("15,19%") == 15.19
    assert _br_num("0,00") == 0.0
    assert _br_num("1.234,56") == 1234.56
    assert _br_num("") is None
    assert _br_num("N/D") is None
    assert _br_num(None) is None


_HTML = """
<table>
<tr><th>Papel</th><th>Segmento</th><th>Cotação</th><th>FFO Yield</th>
<th>Dividend Yield</th><th>P/VP</th><th>Valor de Mercado</th><th>Liquidez</th>
<th>Qtd de imóveis</th><th>Preço do m2</th><th>Aluguel por m2</th>
<th>Cap Rate</th><th>Vacância Média</th><th>Endereço</th></tr>
<tr><td>HGLG11</td><td>Logística</td><td>160,00</td><td>8,50%</td>
<td>9,20%</td><td>0,98</td><td>5.000.000.000</td><td>3.500.000</td>
<td>25</td><td>0,00</td><td>0,00</td><td>8,00%</td><td>3,50%</td><td>SP</td></tr>
<tr><td>MXRF11</td><td>Títulos e Val. Mob.</td><td>10,00</td><td>13,00%</td>
<td>12,50%</td><td>1,01</td><td>4.000.000.000</td><td>8.000.000</td>
<td>0</td><td>0,00</td><td>0,00</td><td>0,00%</td><td>0,00%</td><td></td></tr>
</table>
"""


def test_parse_extrai_campos():
    d = parsear_tabela_fiis(_HTML)
    assert set(d.keys()) == {"HGLG11", "MXRF11"}
    hglg = d["HGLG11"]
    assert hglg["segmento_fii"] == "logística"
    assert hglg["p/vp"] == 0.98
    assert hglg["dy%"] == 9.2
    assert hglg["liquidez_diaria"] == 3500000.0
    assert hglg["qtd_imoveis"] == 25
    assert hglg["cap_rate%"] == 8.0
    assert hglg["vacancia%"] == 3.5
    assert hglg["ffo_yield%"] == 8.5


def test_parse_fii_papel_zera_imovel():
    d = parsear_tabela_fiis(_HTML)
    mxrf = d["MXRF11"]
    assert mxrf["qtd_imoveis"] == 0
    assert mxrf["vacancia%"] == 0.0
    assert mxrf["cap_rate%"] == 0.0
    assert mxrf["liquidez_diaria"] == 8000000.0


def test_parse_html_vazio():
    assert parsear_tabela_fiis("") == {}
    assert parsear_tabela_fiis("<html>sem tabela</html>") == {}
