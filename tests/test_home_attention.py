"""A apresentação dos sinais preserva ranking, acesso completo e links de análise."""
from html.parser import HTMLParser
from textwrap import dedent
from urllib.parse import parse_qs, urlsplit

from streamlit.testing.v1 import AppTest


class SignalParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.titles = []
        self.links = []
        self.in_title = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "strong" and attributes.get("class") == "ft-attention-title":
            self.in_title = True
        if tag == "a" and attributes.get("class") == "ft-attention-card":
            self.links.append(attributes["href"])

    def handle_endtag(self, tag):
        if tag == "strong":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.titles.append(data)


def test_attention_panel_exposes_all_signals_and_keeps_ranked_links():
    at = AppTest.from_string(dedent('''
        import streamlit as st
        from utils.atencao_hoje import coletar_atencao_hoje
        from utils.components import attention_panel
        st.session_state["session_token"] = "fixture token"
        tickers = [f"T{i}.SA" for i in range(9)]
        itens = coletar_atencao_hoje(tickers, {}, {t: {"rsi_14": 29-i} for i, t in enumerate(tickers)}, limite=20)
        attention_panel(itens)
    '''))
    at.query_params.update({"theme": "papel", "profile": "caderno", "density": "compacta"})
    at.run()
    assert not at.exception
    initial = SignalParser(at.markdown[0].value)
    remaining = SignalParser(at.markdown[1].value)
    assert "6 de 9 sinais" in at.markdown[0].value
    assert len(initial.titles) == 6
    assert len(remaining.titles) == 3
    assert initial.titles + remaining.titles == [f"T{i}.SA · sobrevendido" for i in range(8, -1, -1)]
    assert at.expander[0].label == "Mais 3 sinais"
    for i, link in zip(range(8, -1, -1), initial.links + remaining.links):
        assert parse_qs(urlsplit(link).query) == {
            "research_ticker": [f"T{i}.SA"], "s": ["fixture token"],
            "theme": ["papel"], "profile": ["caderno"], "density": ["compacta"],
        }


def test_attention_panel_escapes_event_content_and_recovers_unknown_tone():
    at = AppTest.from_string(dedent('''
        from utils.components import attention_panel
        attention_panel([{"tipo": "evento", "titulo": "<img src=x onerror=alert(1)>", "detalhe": "<script>x</script>", "tom": "bad; color:red"}])
    ''')).run()
    assert not at.exception
    markup = at.markdown[0].value
    assert "<img" not in markup and "<script>" not in markup
    assert "&lt;img" in markup and "&lt;script&gt;" in markup
    assert "--attention-tone:var(--accent)" in markup
    assert "bad; color:red" not in markup
    assert not at.expander


def test_attention_cache_is_scoped_to_received_watchlist():
    """Trocar os tickers deve recarregar sinais; repetir a lista usa o cache."""
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "Home.py").read_text(encoding="utf-8")
    definition = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == "_coletar_atencao_home")
    first_line = min([definition.lineno] + [decorator.lineno for decorator in definition.decorator_list])
    cached_collector = "\n".join(source.splitlines()[first_line - 1:definition.end_lineno])
    app_source = dedent('''
        import streamlit as st
        import sys
        from types import ModuleType
        from unittest.mock import patch
        from utils.atencao_hoje import coletar_atencao_hoje
        st.session_state["fixture_history_calls"] = []
        fixture_db = ModuleType("database.db")
        def history(ticker, dias):
            st.session_state["fixture_history_calls"].append(ticker)
            return [{"score": 70}, {"score": 40}]
        fixture_db.get_historico_score = history
        fixture_db.get_all_price_cache = lambda: {}
        fixture_divergence = ModuleType("utils.divergencia_live")
        fixture_divergence.divergencias_b_br = lambda context: []
        _calendario_macro_home = lambda: []
    ''') + cached_collector + dedent('''

        with patch.dict(sys.modules, {"database.db": fixture_db, "utils.divergencia_live": fixture_divergence}):
            for ticker in ("AT_CACHE_A", "AT_CACHE_B", "AT_CACHE_A"):
                st.text(_coletar_atencao_home((ticker,))[0]["ticker"])
        st.text(",".join(st.session_state["fixture_history_calls"]))
    ''')
    at = AppTest.from_string(app_source).run()
    assert not at.exception
    assert [text.value for text in at.text] == ["AT_CACHE_A", "AT_CACHE_B", "AT_CACHE_A", "AT_CACHE_A,AT_CACHE_B"]
