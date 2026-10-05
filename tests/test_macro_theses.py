"""Autoria, append-only, importação e confirmação real da gravação de teses."""
import json
from datetime import date
import pytest
from utils.macro_theses import (
    nova_tese,revisar_tese,validar_tese,serializar_tese,ler_registro,
    teses_do_usuario,ultimas_revisoes,salvar_tese,exportar_tese,importar_tese,
    alertas_tese,contexto_seguro,eh_tese_macro,usuario_servidor,preparar_rascunho,
)


def thesis(uid=7):
    return nova_tese(uid,'Inflação desacelerando','BR',12,'A desaceleração pode alterar o desconto.',
        ['Núcleos cedendo'],['Serviços persistentes'],'Confirmar três leituras','Núcleo reacelerar','2026-10-10',
        contexto_seguro({'selic':12,'session_token':'não exportar'},'desinflação',portfolio_id=8))


def row(t,uid=None):
    return {'tipo':'tese_macro','user_id':uid if uid is not None else t['autor_id'],'tese':serializar_tese(t)}


def test_ownership_and_version_history_are_isolated():
    t = thesis()
    v2 = revisar_tese(t,7,status='em_revisao')
    historico = teses_do_usuario([row(t),row(v2),row(thesis(8))],7)
    assert len(historico) == 2
    assert ultimas_revisoes(historico) == [v2]
    assert t['revisao'] == 1 and t['status'] == 'ativa'
    with pytest.raises(ValueError):
        revisar_tese(t,8,status='encerrada')
    with pytest.raises(ValueError):
        revisar_tese(t,7,autor_id=8)


def test_server_and_payload_authors_must_both_match():
    assert ler_registro(row(thesis(),8),7) is None
    assert ler_registro(row(thesis(8),7),7) is None
    assert ler_registro({'tipo':'compra','user_id':7,'tese':serializar_tese(thesis())},7) is None


def test_save_is_append_only_and_requires_server_readback():
    rows = []
    def writer(ticker,tipo,data,preco,quantidade,texto):
        assert ticker == 'MACRO' and tipo == 'tese_macro'
        assert preco is quantidade is None
        rows.append({'tipo':tipo,'user_id':7,'tese':texto})
    t = thesis()
    assert salvar_tese(t,user_id_fn=lambda:7,registrar_fn=writer,listar_fn=lambda:rows) == t
    v2 = revisar_tese(t,7,status='encerrada')
    salvar_tese(v2,user_id_fn=lambda:7,registrar_fn=writer,listar_fn=lambda:rows)
    assert len(rows) == 2
    assert salvar_tese(v2,user_id_fn=lambda:7,registrar_fn=writer,listar_fn=lambda:rows) == v2
    with pytest.raises(ValueError):
        salvar_tese(t,user_id_fn=lambda:7,registrar_fn=writer,listar_fn=lambda:rows)
    assert len(rows) == 2


def test_actual_save_error_and_silent_noop_never_claim_success():
    def bad_writer(*args):
        raise RuntimeError('Servidor indisponível')
    with pytest.raises(RuntimeError):
        salvar_tese(thesis(),user_id_fn=lambda:7,registrar_fn=bad_writer,listar_fn=lambda:[])
    with pytest.raises(RuntimeError,match='não confirmada'):
        salvar_tese(thesis(),user_id_fn=lambda:7,registrar_fn=lambda *args:None,listar_fn=lambda:[])
    with pytest.raises(ValueError,match='Autor'):
        salvar_tese(thesis(),user_id_fn=lambda:8,registrar_fn=bad_writer,listar_fn=lambda:[])


def test_import_is_a_new_copy_under_current_author_and_snapshot_has_no_secret():
    t = thesis(8)
    importada = importar_tese(exportar_tese(t),7)
    assert importada['autor_id'] == 7
    assert importada['id_tese'] != t['id_tese']
    assert importada['revisao'] == 1
    assert 'session_token' not in exportar_tese(importada)
    assert importada['contexto']['portfolio_id'] == '8'


@pytest.mark.parametrize('conteudo',['{}','[]','not json',json.dumps({'formato':'outro','versao':1}),json.dumps({'formato':'finterminal-tese-macro','versao':99})])
def test_invalid_import_is_rejected(conteudo):
    with pytest.raises(ValueError):
        importar_tese(conteudo,7)


@pytest.mark.parametrize('campo,valor',[('autor_id',True),('horizonte_meses',0),('revisao',-1),('revisar_em','ontem'),('hipotese',''),('evidencias_favor',{'x':'y'})])
def test_malformed_records_are_rejected(campo,valor):
    t = thesis()
    t[campo] = valor
    with pytest.raises(ValueError):
        validar_tese(t)


def test_overdue_and_regime_change_do_not_auto_invalidate():
    t = thesis()
    alerts = alertas_tese(t,{'quadrante':'reaceleração'},hoje=date(2026,10,11))
    assert len(alerts) == 2
    assert t['status'] == 'ativa'
    assert alertas_tese(revisar_tese(t,7,status='encerrada'),hoje=date(2026,10,11)) == []


def test_macro_records_are_distinguished_from_trades_even_if_type_is_corrupt():
    assert eh_tese_macro(row(thesis()))
    assert eh_tese_macro({'tipo':'compra','tese':serializar_tese(thesis())})
    assert not eh_tese_macro({'tipo':'compra','tese':'Tese: crescimento de lucro'})


def test_server_author_never_falls_back_to_admin(monkeypatch):
    import utils.auth as auth
    import database.db as db
    monkeypatch.setattr(auth,'get_current_user',lambda:None)
    monkeypatch.setattr(db,'get_user_id',lambda:1)
    with pytest.raises(ValueError):
        usuario_servidor()
    monkeypatch.setattr(auth,'get_current_user',lambda:{'user_id':7})
    with pytest.raises(ValueError):
        usuario_servidor()


def test_view_on_database_failure_keeps_draft_without_false_success(monkeypatch):
    import utils.macro_theses_view as view
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(view,'usuario_servidor',lambda:7)
    def failed():
        raise RuntimeError('offline')
    monkeypatch.setattr(view,'carregar_teses',failed)
    at = AppTest.from_string('''
from utils.macro_theses_view import render_teses_macro
render_teses_macro(key_prefix='thesis_test')
''').run(timeout=20)
    assert not at.exception
    assert any('indisponível' in w.value for w in at.warning)
    at.text_input[0].set_value('Minha hipótese')
    for i,texto in enumerate(['Hipótese','A favor','Entrada','Contra','Invalidação']):
        at.text_area[i].set_value(texto)
    next(b for b in at.button if b.label == 'Salvar tese').click().run()
    assert not at.exception
    assert any('não salvo' in e.value for e in at.error)
    assert not at.success
    assert at.session_state['thesis_test_7_global_rascunho']['autor_id'] == 7

def test_view_saves_and_revises_persistent_record_without_rewriting_history(monkeypatch):
    import utils.auth as auth
    import database.db as db
    from streamlit.testing.v1 import AppTest
    rows = []
    monkeypatch.setattr(auth,'get_current_user',lambda:{'user_id':7})
    monkeypatch.setattr(db,'get_user_id',lambda:7)
    monkeypatch.setattr(db,'listar_teses_macro',lambda:rows)
    def writer(ticker,tipo,data,preco,quantidade,texto):
        rows.append({'tipo':tipo,'user_id':7,'tese':texto})
    monkeypatch.setattr(db,'registrar_decisao',writer)
    at = AppTest.from_string('''
from utils.macro_theses_view import render_teses_macro
render_teses_macro(key_prefix='thesis_save_test')
''').run(timeout=20)
    at.text_input[0].set_value('Tese persistente')
    for i,texto in enumerate(['Hipótese','A favor','Entrada','Contra','Invalidação']):
        at.text_area[i].set_value(texto)
    next(b for b in at.button if b.label == 'Salvar tese').click().run()
    assert not at.exception
    assert len(rows) == 1
    assert any('confirmada' in s.value for s in at.success)
    assert at.selectbox[0].value == ler_registro(rows[0],7)['id_tese']
    at.text_area[0].set_value('Hipótese revisada após novos dados')
    next(b for b in at.button if b.label == 'Salvar nova revisão').click().run()
    assert not at.exception
    assert len(rows) == 2
    assert ler_registro(rows[0],7)['hipotese'] == 'Hipótese'
    assert ler_registro(rows[1],7)['hipotese'] == 'Hipótese revisada após novos dados'
    assert ler_registro(rows[1],7)['revisao'] == 2


def test_interrupted_readback_can_retry_exact_draft_without_duplicate_insert():
    rows, reads = [], []
    t = thesis()
    def reader():
        reads.append(None)
        if len(reads) == 2:
            raise RuntimeError('Resposta de confirmação interrompida')
        return rows
    def writer(*args):
        rows.append({'tipo':'tese_macro','user_id':7,'tese':args[-1]})
    with pytest.raises(RuntimeError):
        salvar_tese(t,user_id_fn=lambda:7,registrar_fn=writer,listar_fn=reader)
    assert len(rows) == 1
    assert salvar_tese(t,user_id_fn=lambda:7,registrar_fn=writer,listar_fn=reader) == t
    assert len(rows) == 1
    changed = {**t,'hipotese':'Outra hipótese'}
    with pytest.raises(ValueError,match='desatualizada'):
        salvar_tese(changed,user_id_fn=lambda:7,registrar_fn=writer,listar_fn=reader)
    assert len(rows) == 1


def test_prepared_draft_keeps_identity_and_context_for_retries_and_field_edits():
    t = thesis()
    names = ('titulo','regiao','horizonte_meses','hipotese','evidencias_favor',
             'evidencias_contra','entrada','invalidacao','revisar_em','status','contexto')
    fields = {k:t[k] for k in names}
    first = preparar_rascunho(7,fields)
    fresh_fields = {**fields,'contexto':contexto_seguro({'selic':14},'outro quadrante')}
    assert preparar_rascunho(7,fresh_fields,anterior=first) == first
    edited = preparar_rascunho(7,{**fresh_fields,'hipotese':'Hipótese alterada'},anterior=first)
    assert edited['id_tese'] == first['id_tese']
    assert edited['revisao'] == 1 and edited['criado_em'] == first['criado_em']
    assert edited['hipotese'] == 'Hipótese alterada'
    revision = preparar_rascunho(7,fields,original=t)
    assert revision['id_tese'] == t['id_tese'] and revision['revisao'] == 2
    assert preparar_rascunho(7,fresh_fields,original=t,anterior=revision) == revision


def test_view_retry_after_uncertain_write_keeps_single_thesis(monkeypatch):
    import utils.auth as auth
    import database.db as db
    from streamlit.testing.v1 import AppTest
    rows, reads, writes = [], [], []
    monkeypatch.setattr(auth,'get_current_user',lambda:{'user_id':7})
    monkeypatch.setattr(db,'get_user_id',lambda:7)
    def reader():
        reads.append(None)
        if len(reads) == 3:
            raise RuntimeError('Readback interrompido')
        return rows
    def writer(*args):
        writes.append(None)
        rows.append({'tipo':'tese_macro','user_id':7,'tese':args[-1]})
    monkeypatch.setattr(db,'listar_teses_macro',reader)
    monkeypatch.setattr(db,'registrar_decisao',writer)
    at = AppTest.from_string("from utils.macro_theses_view import render_teses_macro\nrender_teses_macro(key_prefix='thesis_retry')").run(timeout=20)
    at.text_input[0].set_value('Tese com resposta interrompida')
    for i,texto in enumerate(['Hipótese','A favor','Entrada','Contra','Invalidação']):
        at.text_area[i].set_value(texto)
    next(b for b in at.button if b.label == 'Salvar tese').click().run()
    assert not at.exception and at.error and not at.success
    draft_id = at.session_state['thesis_retry_7_global_rascunho']['id_tese']
    next(b for b in at.button if b.label == 'Salvar tese').click().run()
    assert not at.exception and at.success
    assert len(rows) == len(writes) == 1
    assert ler_registro(rows[0],7)['id_tese'] == draft_id
    assert at.selectbox[0].value == draft_id


def test_draft_export_tracks_selected_form_instead_of_previous_thesis(monkeypatch):
    import utils.macro_theses_view as view
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(view,'usuario_servidor',lambda:7)
    existing = thesis()
    monkeypatch.setattr(view,'carregar_teses',lambda:[existing])
    at = AppTest.from_string("from utils.macro_theses_view import render_teses_macro\nrender_teses_macro(key_prefix='thesis_export_scope')").run(timeout=20)
    existing_id = existing['id_tese']
    at.selectbox[0].select(existing_id).run()
    assert any('Exportação:' in c.value for c in at.caption)
    at.selectbox[0].select('Nova tese').run()
    assert not at.exception
    assert not any('Exportação:' in c.value for c in at.caption)
