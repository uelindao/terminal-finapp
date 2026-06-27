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
              "nucleo_dupla_pond": 4.1, "nucleo_ma_suav": 4.3}
    infl3 = {"servicos": 4.0, "administrados": 11.2, "livres": 5.0, "alimentacao": 4.1,
             "nucleo_dupla_pond": 5.5, "nucleo_ma_suav": 5.0}

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
