"""Bancada pessoal de hipóteses macro; persistência Supabase via decision_log."""
from datetime import date, timedelta
import streamlit as st
from utils.components import section_title, portfolio_kpis
from utils.macro_theses import (
    carregar_teses, ultimas_revisoes, usuario_servidor, preparar_rascunho,
    salvar_tese, importar_tese, exportar_tese, contexto_seguro, alertas_tese, STATUS, REGIOES, hoje_local,
)


def render_teses_macro(macro_context=None, quadrante=None, horizonte_meses=6,
                       key_prefix='macro_theses', portfolio_id=None):
    section_title('Teses macro')
    st.caption('Hipótese, evidências, condições e revisão. Cada atualização cria uma versão; o histórico permanece preservado.')
    try:
        uid = usuario_servidor()
    except ValueError as exc:
        st.info(str(exc))
        return
    key = f'{key_prefix}_{uid}_{portfolio_id or "global"}'
    ctx = contexto_seguro(macro_context,quadrante,portfolio_id)
    falha_banco = False
    try:
        historico = carregar_teses()
    except Exception:
        historico, falha_banco = [], True
        st.warning('Diário no servidor indisponível. Você pode preparar e exportar um rascunho; nada foi salvo.')
    atuais = ultimas_revisoes(historico)
    if portfolio_id is not None:
        atuais = [t for t in atuais if t['contexto'].get('portfolio_id') in (None,str(portfolio_id))]
    if st.session_state.pop(key+'_sucesso',False):
        st.success('Versão confirmada no diário do servidor.')
    vencidas = sum(bool(alertas_tese(t,ctx)) for t in atuais)
    portfolio_kpis([
        {'nome':'Teses','valor':str(len(atuais)),'sublabel':'última versão de cada hipótese'},
        {'nome':'Revisões','valor':str(len(historico)),'sublabel':'histórico preservado'},
        {'nome':'A revisar','valor':str(vencidas),'sublabel':'data prevista ou contexto mudou','tone':'amber'},
    ])
    with st.expander('Importar uma tese',expanded=False):
        upload = st.file_uploader('Arquivo JSON exportado pelo terminal',type=['json'],key=key+'_upload')
        st.caption('A importação prepara uma cópia nova, vinculada à sua conta; a tese original permanece intacta.')
        if upload is not None and st.button('Preparar cópia',key=key+'_import'):
            try:
                st.session_state[key+'_importada'] = importar_tese(upload.getvalue(),uid)
                st.rerun()
            except (ValueError,UnicodeError) as exc:
                st.error(str(exc))
    importada = st.session_state.get(key+'_importada')
    options = ['Nova tese'] + (['Importação preparada'] if importada else []) + [t['id_tese'] for t in atuais]
    por_id = {t['id_tese']:t for t in atuais}
    pendente = st.session_state.pop(key+'_abrir_next',None)
    if pendente in options:
        st.session_state[key+'_escolha'] = pendente
    escolha = st.selectbox('Criar ou revisar',options,key=key+'_escolha',
        format_func=lambda x:f"{por_id[x]['titulo']} · v{por_id[x]['revisao']}" if x in por_id else x)
    original = por_id.get(escolha)
    base = original or (importada if escolha == 'Importação preparada' else {}) or {}
    form_key = key+'_form_'+str(base.get('id_tese','nova'))+'_'+str(base.get('revisao',0))
    with st.form(form_key):
        titulo = st.text_input('Título da hipótese',value=base.get('titulo',''),max_chars=180)
        a,b,c = st.columns([1,1,1])
        with a:
            regiao = st.selectbox('Região',REGIOES,index=REGIOES.index(base.get('regiao','BR')))
        with b:
            horizonte = st.number_input('Horizonte em meses',min_value=1,max_value=60,
                                       value=int(base.get('horizonte_meses',horizonte_meses)))
        with c:
            revisar_em = st.date_input('Próxima revisão',value=date.fromisoformat(base['revisar_em']) if base.get('revisar_em') else hoje_local()+timedelta(days=30))
        hipotese = st.text_area('Hipótese e mecanismo econômico',value=base.get('hipotese',''),height=100,max_chars=5000)
        a,b = st.columns(2)
        with a:
            favor = st.text_area('Evidências favoráveis · uma por linha',value='\n'.join(base.get('evidencias_favor',[])),height=100,max_chars=10000)
            entrada = st.text_area('Condições para iniciar ou ampliar a rotação',value=base.get('entrada',''),height=90,max_chars=5000)
        with b:
            contra = st.text_area('Evidências contrárias · uma por linha',value='\n'.join(base.get('evidencias_contra',[])),height=100,max_chars=10000)
            invalidacao = st.text_area('O que invalida a hipótese?',value=base.get('invalidacao',''),height=90,max_chars=5000)
        status = st.selectbox('Estado da tese',STATUS,index=STATUS.index(base.get('status','ativa')),
                              format_func=lambda x:x.replace('_',' ').capitalize())
        col_a,col_b = st.columns(2)
        with col_a:
            preparar = st.form_submit_button('Preparar rascunho para exportar',width='stretch')
        with col_b:
            salvar = st.form_submit_button('Salvar nova revisão' if original else 'Salvar tese',type='primary',width='stretch')
    if preparar or salvar:
        try:
            campos = dict(titulo=titulo,regiao=regiao,horizonte_meses=int(horizonte),hipotese=hipotese,
                evidencias_favor=[v.strip() for v in favor.splitlines() if v.strip()],
                evidencias_contra=[v.strip() for v in contra.splitlines() if v.strip()],entrada=entrada,
                invalidacao=invalidacao,revisar_em=revisar_em.isoformat(),status=status,contexto={**ctx,'portfolio_id':original['contexto'].get('portfolio_id')} if original else ctx)
            anterior = st.session_state.get(key+'_rascunho') if st.session_state.get(key+'_rascunho_form_key') == form_key else None
            rascunho = preparar_rascunho(uid,campos,original,anterior)
            st.session_state[key+'_rascunho'] = rascunho
            st.session_state[key+'_rascunho_form_key'] = form_key
            if salvar:
                if falha_banco:
                    raise RuntimeError('Servidor indisponível. Rascunho preparado, mas não salvo.')
                salvar_tese(rascunho)
                st.session_state[key+'_sucesso'] = True
                st.session_state[key+'_abrir_next'] = rascunho['id_tese']
                st.rerun()
            else:
                st.info('Rascunho preparado localmente. Use a exportação abaixo para guardá-lo.')
        except (ValueError,RuntimeError) as exc:
            st.error(str(exc))
        except Exception:
            st.error('Não foi possível confirmar a gravação no servidor. Seu rascunho pode ser exportado abaixo.')
    draft = st.session_state.get(key+'_rascunho') if st.session_state.get(key+'_rascunho_form_key') == form_key else None
    if draft is None:
        draft = original or (importada if escolha == 'Importação preparada' else None)
    if draft:
        st.caption(f"Exportação: {draft['titulo']} · v{draft['revisao']}")
        st.download_button('Exportar tese em JSON',data=exportar_tese(draft),mime='application/json',
            file_name=f"tese_macro_{draft['id_tese']}_v{draft['revisao']}.json",key=key+'_export')
        with st.expander('Contexto registrado',expanded=False):
            st.json(draft['contexto'])
    if atuais:
        section_title('Hipóteses acompanhadas')
        filtro = st.selectbox('Filtrar estado',['Todos',*STATUS],key=key+'_filtro',format_func=lambda x:x.replace('_',' ').capitalize())
        for tese in atuais:
            if filtro != 'Todos' and tese['status'] != filtro:
                continue
            avisos = alertas_tese(tese,ctx)
            with st.expander(f"{tese['titulo']} · {tese['regiao']} · {tese['horizonte_meses']}m · v{tese['revisao']}",expanded=bool(avisos)):
                if avisos:
                    st.warning(' · '.join(avisos))
                st.markdown(tese['hipotese'])
                st.caption(f"Estado: {tese['status'].replace('_',' ')} · Próxima revisão: {tese['revisar_em']}")
                a,b = st.columns(2)
                with a:
                    st.markdown('**A favor**')
                    for texto in tese['evidencias_favor']:
                        st.write('• '+texto)
                    st.markdown('**Condição de entrada**')
                    st.write(tese['entrada'])
                with b:
                    st.markdown('**Contra**')
                    for texto in tese['evidencias_contra']:
                        st.write('• '+texto)
                    st.markdown('**Invalidação**')
                    st.write(tese['invalidacao'])
                revisoes = [t for t in historico if t['id_tese'] == tese['id_tese']]
                st.caption('Revisões anteriores permanecem disponíveis no arquivo de cada versão.')
                for indice_revisao,revisao in enumerate(sorted(revisoes,key=lambda t:(t['revisao'],t['revisado_em']),reverse=True)):
                    st.download_button(f"Exportar v{revisao['revisao']} · {revisao['revisado_em'][:10]}",
                        data=exportar_tese(revisao),mime='application/json',
                        file_name=f"tese_{tese['id_tese']}_v{revisao['revisao']}.json",
                        key=f"{key}_historico_{tese['id_tese']}_{revisao['revisao']}_{indice_revisao}")
    else:
        st.info('Registre a primeira hipótese com evidências e condições de revisão.')
