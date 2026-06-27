"""
Teste do bloco de inflação setorial nos prompts de IA (utils/ai_prompts).
"""
from unittest.mock import patch

from utils.ai_prompts import bloco_inflacao_setorial, _mom_label


def test_mom_label():
    assert "acelerando" in _mom_label(6.0, 5.0)
    assert "desacelerando" in _mom_label(4.0, 6.0)
    assert "estável" in _mom_label(5.0, 5.0)
    assert _mom_label(None, 5.0) == ""


def test_bloco_vazio_sem_snapshot():
    # sem dados de inflação → bloco vazio (degrada gracioso, não quebra o prompt)
    with patch("utils.inflation_sectoral.get_inflacao_atual", return_value={}):
        assert bloco_inflacao_setorial("Financial Services", "BR") == ""


def test_bloco_decomposicao_e_momentum_br():
    infl12 = {"servicos": 6.0, "administrados": 5.8, "livres": 5.0, "alimentacao": 3.9,
              "nucleo_dupla_pond": 4.1, "nucleo_ma_suav": 4.3,
              "igpm": 7.0, "ipca_cheio": 4.5}
    infl3 = {"servicos": 4.0, "administrados": 11.2, "livres": 5.0, "alimentacao": 4.1,
             "nucleo_dupla_pond": 5.5, "nucleo_ma_suav": 5.0,
             "igpm": 9.0, "ipca_cheio": 4.0}

    def _fake(market, horizonte=None):
        return infl3 if horizonte == "3m" else infl12

    with (
        patch("utils.inflation_sectoral.get_inflacao_atual", side_effect=_fake),
        patch("utils.inflation_sectoral.pressao_inflacao_setor",
              return_value={"motivos": ["receita indexada (90%) → proteção de margem"]}),
    ):
        txt = bloco_inflacao_setorial("Real Estate", "BR")

    assert "inflação decomposta" in txt
    assert "serviços" in txt and "desacelerando" in txt   # 6.0 → 4.0
    assert "administrados" in txt and "acelerando" in txt  # 5.8 → 11.2
    assert "núcleo" in txt
    assert "exposição deste setor" in txt
    assert "gap de margem" in txt and "comprime margem" in txt   # 7.0−4.5 = +2.5pp


def test_gap_margem():
    from utils.inflation_sectoral import gap_margem
    with patch("utils.inflation_sectoral.get_inflacao_atual",
               return_value={"igpm": 7.0, "ipca_cheio": 4.5}):
        g = gap_margem("BR")
    assert g["gap"] == 2.5 and g["produtor"] == 7.0 and g["consumidor"] == 4.5
    # US: ppi − core
    with patch("utils.inflation_sectoral.get_inflacao_atual",
               return_value={"ppi": 1.5, "core": 3.5}):
        g2 = gap_margem("US")
    assert g2["gap"] == -2.0           # produtor < consumidor → alívio de margem
    # sem dados → None
    with patch("utils.inflation_sectoral.get_inflacao_atual", return_value={}):
        assert gap_margem("BR") is None
