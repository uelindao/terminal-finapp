"""Histórico paginado e isolado do diário macro, sem servidor real."""
from types import SimpleNamespace
import pytest
import database.db as db
import utils.auth as auth


class FakeSupabase:
    def __init__(self, rows, cap=500, fail_from=None, malformed=None):
        self.rows, self.cap, self.fail_from, self.malformed = rows, cap, fail_from, malformed
        self.calls = []

    def table(self, name):
        assert name == 'decision_log'
        outer = self
        class Query:
            def __init__(self):
                self.filters = {}
            def select(self, fields):
                assert fields == '*'
                return self
            def eq(self, field, value):
                self.filters[field] = value
                return self
            def order(self, field):
                assert field == 'id'
                return self
            def range(self, start, end):
                self.start, self.end = start, end
                return self
            def execute(self):
                outer.calls.append((dict(self.filters),self.start,self.end))
                if outer.fail_from is not None and self.start >= outer.fail_from:
                    raise RuntimeError('Página indisponível')
                if outer.malformed is not None:
                    return SimpleNamespace(data=outer.malformed)
                selected = [r for r in outer.rows if all(r.get(k) == v for k,v in self.filters.items())]
                selected.sort(key=lambda r:r['id'])
                return SimpleNamespace(data=selected[self.start:self.end+1][:outer.cap])
        return Query()


@pytest.fixture
def server_identity(monkeypatch):
    monkeypatch.setattr(db,'get_user_id',lambda:7)
    monkeypatch.setattr(auth,'get_current_user',lambda:{'user_id':7})


@pytest.mark.parametrize('server_cap', [500,37])
def test_all_pages_loaded_with_server_identity_and_type_filters(monkeypatch,server_identity,server_cap):
    rows = [{'id':i,'user_id':7,'tipo':'tese_macro'} for i in range(1,1235)]
    rows += [{'id':9000,'user_id':8,'tipo':'tese_macro'}, {'id':9001,'user_id':7,'tipo':'compra'}]
    sb = FakeSupabase(rows,cap=server_cap)
    monkeypatch.setattr(db,'get_supabase',lambda:sb)
    result = db.listar_teses_macro()
    assert len(result) == 1234
    assert [r['id'] for r in result] == list(range(1,1235))
    assert len(sb.calls) > 3
    assert all(filters == {'user_id':7,'tipo':'tese_macro'} for filters,_,_ in sb.calls)
    assert sb.calls[1][1] == server_cap
    assert sb.calls[-1][1] == 1234


def test_later_page_error_is_propagated_instead_of_empty_or_partial_history(monkeypatch,server_identity):
    sb = FakeSupabase([{'id':i,'user_id':7,'tipo':'tese_macro'} for i in range(1,800)],fail_from=500)
    monkeypatch.setattr(db,'get_supabase',lambda:sb)
    with pytest.raises(RuntimeError,match='Página indisponível'):
        db.listar_teses_macro()
    assert len(sb.calls) == 2


@pytest.mark.parametrize('current_user', [None,{'user_id':8},{'user_id':True},{'user_id':'7'}])
def test_invalid_identity_cannot_open_server_or_fallback_to_admin(monkeypatch,current_user):
    monkeypatch.setattr(db,'get_user_id',lambda:7)
    monkeypatch.setattr(auth,'get_current_user',lambda:current_user)
    def unexpected_connection():
        pytest.fail('Não deve acessar o servidor sem identidade autenticada válida')
    monkeypatch.setattr(db,'get_supabase',unexpected_connection)
    with pytest.raises(ValueError,match='Sessão autenticada'):
        db.listar_teses_macro()


def test_inconsistent_pagination_never_loops_or_claims_complete_history(monkeypatch,server_identity):
    duplicate_rows = [{'id':1,'user_id':7,'tipo':'tese_macro'}] * 2
    monkeypatch.setattr(db,'get_supabase',lambda:FakeSupabase(duplicate_rows))
    with pytest.raises(RuntimeError,match='Paginação'):
        db.listar_teses_macro()


def test_wrongly_scoped_response_is_rejected_even_if_backend_filter_failed(monkeypatch,server_identity):
    sb = FakeSupabase([],malformed=[{'id':1,'user_id':8,'tipo':'tese_macro'}])
    monkeypatch.setattr(db,'get_supabase',lambda:sb)
    with pytest.raises(RuntimeError,match='conta autenticada'):
        db.listar_teses_macro()
