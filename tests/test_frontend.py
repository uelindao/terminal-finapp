"""Behavioral checks for the shared interface, isolated from external services."""
from pathlib import Path
from textwrap import dedent
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def app(source):
    test = AppTest.from_string(dedent(source), default_timeout=15).run()
    assert not test.exception, [item.message for item in test.exception]
    return test


def test_section_selection_survives_rerun_and_deselect():
    at = app('''
        import streamlit as st
        from utils.components import section_selector
        value = section_selector(["📊 resumo", "📐 risco"], "section")
        st.text(value)
    ''')
    widget = at.get("button_group")[0]
    assert widget.options == ["Resumo", "Risco"]
    widget.set_value("📐 risco").run()
    assert at.text[0].value == "📐 risco"
    at.run()
    assert at.text[0].value == "📐 risco"
    at.get("button_group")[0].set_value(None).run()
    assert not at.exception
    assert at.text[0].value == "📐 risco"


def test_obsolete_section_is_recovered_when_options_change():
    at = app('''
        import streamlit as st
        from utils.components import section_selector
        if "section" not in st.session_state:
            st.session_state["section"] = "Seção removida"
        st.text(section_selector(["Conta", "Aparência"], "section"))
    ''')
    assert at.text[0].value == "Conta"


def test_url_filter_restores_deep_link_and_updates_query():
    at = AppTest.from_string(dedent('''
        import streamlit as st
        from utils.components import url_state_chip_filter_row
        st.text(url_state_chip_filter_row(["Brasil", "EUA"], "market"))
    '''))
    at.query_params["market"] = "eua"
    at.run()
    assert not at.exception
    assert at.text[0].value == "EUA"
    at.get("button_group")[0].set_value("Brasil").run()
    assert at.query_params["market"] == ["brasil"]
    assert at.text[0].value == "Brasil"
    at.run()
    assert at.text[0].value == "Brasil"


def test_global_search_validates_empty_input_without_provider_request():
    at = app('''
        from utils.components import busca_global_sidebar
        busca_global_sidebar()
    ''')
    with patch("utils.components._resolver_ticker_busca") as resolver:
        at.button[0].click().run()
        assert not at.exception
        assert at.warning[0].value == "Digite um ticker ou nome de empresa."
        resolver.assert_not_called()


def test_global_search_handles_no_result():
    at = app('''
        from utils.components import busca_global_sidebar
        busca_global_sidebar()
    ''')
    with patch("utils.components._resolver_ticker_busca", return_value=None):
        at.text_input[0].set_value("Ativo desconhecido")
        at.button[0].click().run()
    assert not at.exception
    assert "Ativo não encontrado" in at.warning[0].value


def test_watchlist_actions_are_bound_to_the_correct_asset():
    at = app('''
        import streamlit as st
        from utils.components import watchlist_row
        for ticker in ["PETR4.SA", "AAPL"]:
            watchlist_row(ticker, ticker, 35., 1.2, health_score=76, serie_30d=[30., 35.])
    ''')
    at.button(key="mem_AAPL").click().run()
    assert not at.exception
    assert at.session_state["show_memorial_AAPL"] is True
    assert "show_memorial_PETR4.SA" not in at.session_state
    at.button(key="del_PETR4.SA").click().run()
    assert not at.exception
    assert at.session_state["confirm_del_PETR4.SA"] is True
    assert "confirm_del_AAPL" not in at.session_state


def test_removal_requires_confirmation_and_cancel_does_not_execute():
    at = app('''
        import streamlit as st
        from utils.components import confirm_action
        st.session_state.setdefault("removed", False)
        def remove():
            st.session_state["removed"] = True
        if st.button("Remover"):
            confirm_action("Remover item?", "O item será removido.", remove, key="remove")
    ''')
    at.button[0].click().run()
    assert not at.exception
    assert at.session_state["removed"] is False
    at.button(key="remove_cancel").click().run()
    assert at.session_state["removed"] is False
    at.button[0].click().run()
    at.button(key="remove_confirm").click().run()
    assert not at.exception
    assert at.session_state["removed"] is True


def test_login_validates_fields_without_authenticating():
    at = app('''
        from utils.auth import _render_tela_login
        _render_tela_login()
    ''')
    assert [field.label for field in at.text_input] == ["Usuário", "Senha"]
    with patch("utils.auth.autenticar_usuario") as authenticate:
        at.button[0].click().run()
        assert not at.exception
        assert at.warning
        authenticate.assert_not_called()


@pytest.mark.parametrize("theme", ["dark", "light", "papel"])
def test_theme_switch_renders_widgets_on_repeated_runs(theme):
    at = AppTest.from_string(dedent('''
        import streamlit as st
        from utils.style import aplicar_tema
        from utils.themes import set_tema
        from utils.components import page_header, metric_card
        set_tema(st.session_state.get("test_theme", "dark"))
        aplicar_tema()
        page_header("Minha conta", "Suas preferências")
        metric_card("Valor", "R$ 10.000", "Dados da conta")
        st.text_input("Nome")
    '''))
    at.session_state["test_theme"] = theme
    at.run()
    assert not at.exception
    at.text_input[0].set_value("Nome atualizado").run()
    assert not at.exception
    assert at.text_input[0].value == "Nome atualizado"


def test_headers_escape_user_supplied_text():
    at = app('''
        from utils.components import page_header, metric_card
        page_header('<img src=x>', '<script>alert(1)</script>')
        metric_card('Label', '<img src=x>')
    ''')
    rendered = "".join(item.value for item in at.markdown) + "".join(item.proto.body for item in at.get("html"))
    assert "<script>" not in rendered
    assert "<img src=x>" not in rendered
    assert "&lt;img src=x&gt;" in rendered


@pytest.mark.parametrize("theme", ["dark", "light", "papel"])
def test_primary_themes_keep_small_text_readable(theme):
    """WCAG text contrast for the shared small-text and status colors."""
    from utils.themes import TEMAS
    colors = TEMAS[theme]["vars"]
    def luminance(value):
        rgb = [int(value.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in rgb]
        return sum(c * weight for c, weight in zip(linear, (.2126, .7152, .0722)))
    for fg in ("--text-primary", "--text-secondary", "--text-muted", "--accent", "--bull", "--bear", "--amber", "--info"):
        for bg in ("--bg-base", "--bg-surface"):
            a, b = sorted((luminance(colors[fg]), luminance(colors[bg])))
            assert (b + .05) / (a + .05) >= 4.5, (theme, fg, bg)



def test_home_summary_preserves_reais_and_dollars_separately():
    from utils.portfolio_view import currency_totals
    summary = currency_totals({
        "PETR4.SA": {"quantidade": 10, "preco_medio": 25},
        "AAPL": {"quantidade": 2, "preco_medio": 100},
        "MSFT": {"quantidade": 0, "preco_medio": 500},
    }, {"PETR4.SA": 30, "AAPL": 120})
    brl, usd = summary
    assert (brl["currency"], brl["value"], brl["pnl"]) == ("BRL", 300, 50)
    assert (usd["currency"], usd["value"], usd["pnl"]) == ("USD", 240, 40)
    assert usd["positions"] == 1


def test_home_summary_signals_incomplete_quotes():
    from utils.portfolio_view import currency_totals
    summary = currency_totals({"AAPL": {"quantidade": 2, "preco_medio": 100}}, {})
    assert summary[0]["missing_prices"] == 1


def test_home_summary_handles_an_empty_portfolio():
    from utils.portfolio_view import currency_totals
    assert currency_totals({}, {}) == []



@pytest.mark.parametrize("name,symbol", [("Apple", "AAPL"), ("Nubank", "NU"), ("NUBANK", "NU")])
def test_asset_search_resolves_short_company_names(name, symbol):
    from utils.components import _resolver_ticker_busca
    with patch("utils.market_data.buscar_ativo_yahoo", return_value=[{"symbol": symbol}]) as search:
        assert _resolver_ticker_busca(name) == symbol
        search.assert_called_once_with(name)


@pytest.mark.parametrize("query,symbol", [("petr4", "PETR4.SA"), ("HGLG11", "HGLG11.SA"), ("PETR4.SA", "PETR4.SA"), ("aapl", "AAPL")])
def test_asset_search_opens_known_symbols_without_network(query, symbol):
    from utils.components import _resolver_ticker_busca
    with patch("utils.market_data.buscar_ativo_yahoo") as search:
        assert _resolver_ticker_busca(query) == symbol
        search.assert_not_called()


def test_asset_search_does_not_invent_symbols_for_unknown_words():
    from utils.components import _resolver_ticker_busca
    with patch("utils.market_data.buscar_ativo_yahoo", return_value=[]):
        assert _resolver_ticker_busca("XYZABC") is None


def test_section_selection_returns_after_navigation_widget_cleanup():
    at = app('''
        import streamlit as st
        from utils.components import section_selector
        page = st.radio("Página", ["Análise", "Outra página"], key="page")
        if page == "Análise":
            st.text(section_selector(["Preço", "Fundamentos"], "section"))
    ''')
    at.get("button_group")[0].set_value("Fundamentos").run()
    at.radio[0].set_value("Outra página").run()
    assert "section" not in at.session_state
    at.radio[0].set_value("Análise").run()
    assert not at.exception
    assert at.text[0].value == "Fundamentos"
