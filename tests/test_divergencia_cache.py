"""Old, biased divergence snapshots must not leak into the UI."""
import json
import database.db as db
from utils.divergencia_live import estatistica_divergencias_br, metodologia_historica_valida


def test_snapshot_requires_causal_method_and_leaves_legacy_unavailable(monkeypatch):
    valid = {"metodologia": {"versao": 2, "entrada": "apos_confirmacao",
                            "tipo": "estudo_descritivo_retrospectivo", "fora_da_amostra": False},
             "estatistica": {"b": {"13": {"n": 20}}}}
    for payload, expected in [({"estatistica": valid["estatistica"]}, {}),
                              ({**valid, "metodologia": {**valid["metodologia"], "versao": 1}}, {}),
                              (valid, valid)]:
        estatistica_divergencias_br.clear()
        monkeypatch.setattr(db, "get_ai_analysis", lambda **kwargs: {"conteudo": json.dumps(payload)})
        assert estatistica_divergencias_br() == expected
    estatistica_divergencias_br.clear()
    assert not metodologia_historica_valida({})
