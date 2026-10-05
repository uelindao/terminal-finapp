"""Teses macro versionadas no decision_log existente; revisões append-only."""
from __future__ import annotations
import json
from copy import deepcopy
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from uuid import UUID, uuid4
from utils.regime_classifier import valor_observado

PREFIXO = 'FT_MACRO_THESIS_V1:'
TIPO = 'tese_macro'
STATUS = ('ativa', 'em_revisao', 'invalidada', 'encerrada')
REGIOES = ('BR', 'EUA', 'Global')


def hoje_local():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).date()


def _agora():
    return datetime.now(timezone.utc).isoformat()


def _texto(valor, campo, limite=5000, obrigatorio=False):
    if not isinstance(valor, str) or len(valor) > limite or (obrigatorio and not valor.strip()):
        raise ValueError(f'{campo}: texto inválido ou muito longo.')
    return valor.strip()


def contexto_seguro(macro_context=None, quadrante=None, portfolio_id=None):
    contexto = macro_context or {}
    q = quadrante or ''
    if isinstance(q, dict):
        q = q.get('quadrante') or q.get('label') or q.get('regime') or ''
    return {'capturado_em':_agora(), 'quadrante':str(q)[:120],
      'regime':str(contexto.get('regime_label') or contexto.get('regime') or '')[:120],
      'portfolio_id':str(portfolio_id)[:80] if portfolio_id is not None else None,
      'indicadores':{k:valor_observado(contexto,k) for k in
                     ('selic','ipca_12m','vix','treasury_10y','usd_brl')}}


def validar_tese(dados):
    if not isinstance(dados, dict) or dados.get('versao') != 1:
        raise ValueError('Versão de tese não suportada.')
    r = deepcopy(dados)
    try:
        r['id_tese'] = str(UUID(str(r['id_tese'])))
    except (ValueError, KeyError, TypeError):
        raise ValueError('Identificador da tese inválido.') from None
    for campo in ('autor_id','revisao','horizonte_meses'):
        if isinstance(r.get(campo), bool) or not isinstance(r.get(campo), int) or r[campo] <= 0:
            raise ValueError(f'{campo}: inteiro positivo obrigatório.')
    if r['horizonte_meses'] > 60 or r['revisao'] > 100000:
        raise ValueError('Horizonte/revisão fora dos limites.')
    if r.get('status') not in STATUS or r.get('regiao') not in REGIOES:
        raise ValueError('Status ou região inválidos.')
    for campo in ('titulo','hipotese','entrada','invalidacao'):
        r[campo] = _texto(r.get(campo),campo,180 if campo == 'titulo' else 5000,True)
    for campo in ('evidencias_favor','evidencias_contra'):
        if not isinstance(r.get(campo),list) or len(r[campo]) > 100:
            raise ValueError('Evidências devem ser uma lista de até 100 textos.')
        r[campo] = [_texto(x,campo) for x in r[campo] if x != '']
    try:
        date.fromisoformat(r['revisar_em'])
        datetime.fromisoformat(r['criado_em'])
        datetime.fromisoformat(r['revisado_em'])
    except (ValueError, KeyError, TypeError):
        raise ValueError('Datas inválidas na tese.') from None
    c = r.get('contexto')
    if not isinstance(c,dict) or not isinstance(c.get('indicadores'),dict):
        raise ValueError('Contexto da tese inválido.')
    # Reconstrói whitelist; conteúdo importado nunca inclui secrets ou estado de sessão.
    r['contexto'] = {'capturado_em':_texto(c.get('capturado_em',''),'capturado_em',100),
        'regime':_texto(c.get('regime',''),'regime',120),
        'quadrante':_texto(c.get('quadrante',''),'quadrante',120),
        'portfolio_id':str(c['portfolio_id'])[:80] if c.get('portfolio_id') is not None else None,
        'indicadores':{k:valor_observado(c['indicadores'],k) for k in
                       ('selic','ipca_12m','vix','treasury_10y','usd_brl')}}
    permitidos = {'versao','id_tese','revisao','autor_id','titulo','regiao','horizonte_meses','hipotese',
                  'evidencias_favor','evidencias_contra','entrada','invalidacao','revisar_em','status',
                  'criado_em','revisado_em','contexto'}
    return {k:v for k,v in r.items() if k in permitidos}


def nova_tese(autor_id, titulo, regiao, horizonte_meses, hipotese, evidencias_favor,
              evidencias_contra, entrada, invalidacao, revisar_em, contexto=None, status='ativa'):
    agora = _agora()
    return validar_tese({'versao':1,'id_tese':str(uuid4()),'revisao':1,'autor_id':autor_id,
      'titulo':titulo,'regiao':regiao,'horizonte_meses':horizonte_meses,'hipotese':hipotese,
      'evidencias_favor':evidencias_favor,'evidencias_contra':evidencias_contra,
      'entrada':entrada,'invalidacao':invalidacao,'revisar_em':str(revisar_em),'status':status,
      'criado_em':agora,'revisado_em':agora,'contexto':contexto or contexto_seguro()})


def revisar_tese(tese, autor_atual, **alteracoes):
    original = validar_tese(tese)
    if original['autor_id'] != autor_atual:
        raise ValueError('A tese pertence a outra conta.')
    editaveis = {'titulo','regiao','horizonte_meses','hipotese','evidencias_favor',
                 'evidencias_contra','entrada','invalidacao','revisar_em','status','contexto'}
    if set(alteracoes) - editaveis:
        raise ValueError('Campo de identidade/revisão não pode ser alterado.')
    original.update(alteracoes)
    original['revisao'] += 1
    original['revisado_em'] = _agora()
    return validar_tese(original)


def preparar_rascunho(autor_id, campos, original=None, anterior=None):
    """Mantém identidade ao repetir um envio cujo resultado ficou incerto.

    O chamador conserva ``anterior`` somente para o mesmo formulário. Mudanças
    editam o rascunho, mas não criam outra hipótese nem saltam uma revisão.
    """
    novo = revisar_tese(original, autor_id, **campos) if original else nova_tese(autor_id, **campos)
    if anterior is None:
        return novo
    anterior = validar_tese(anterior)
    mesma_base = (anterior['autor_id'] == autor_id and anterior['revisao'] == novo['revisao']
                  and (original is None or anterior['id_tese'] == novo['id_tese']))
    if not mesma_base:
        return novo
    editaveis = ('titulo','regiao','horizonte_meses','hipotese','evidencias_favor',
                 'evidencias_contra','entrada','invalidacao','revisar_em','status')
    if all(anterior[k] == novo[k] for k in editaveis):
        # O contexto/timestamp do envio original também permanece preservado.
        return anterior
    novo['id_tese'], novo['criado_em'] = anterior['id_tese'], anterior['criado_em']
    return validar_tese(novo)


def serializar_tese(tese):
    return PREFIXO + json.dumps(validar_tese(tese),ensure_ascii=False,allow_nan=False,separators=(',',':'))


def ler_registro(registro, autor_id):
    if registro.get('tipo') != TIPO or registro.get('user_id') != autor_id:
        return None
    texto = registro.get('tese')
    if not isinstance(texto,str) or not texto.startswith(PREFIXO) or len(texto) > 1000000:
        return None
    try:
        tese = validar_tese(json.loads(texto[len(PREFIXO):]))
        return tese if tese['autor_id'] == autor_id else None
    except (ValueError, TypeError):
        return None


def teses_do_usuario(registros, autor_id):
    teses = [t for r in registros or [] if (t := ler_registro(r,autor_id)) is not None]
    return sorted(teses,key=lambda t:(t['revisado_em'],t['revisao']),reverse=True)


def ultimas_revisoes(teses):
    ultimas = {}
    for tese in teses:
        anterior = ultimas.get(tese['id_tese'])
        if anterior is None or (tese['revisao'],tese['revisado_em']) > (anterior['revisao'],anterior['revisado_em']):
            ultimas[tese['id_tese']] = tese
    return sorted(ultimas.values(),key=lambda t:t['revisado_em'],reverse=True)


def usuario_servidor():
    from utils.auth import get_current_user
    from database.db import get_user_id
    user = get_current_user()
    uid = user.get('user_id') if user else None
    if isinstance(uid,bool) or not isinstance(uid,int) or uid <= 0 or get_user_id() != uid:
        raise ValueError('Sessão autenticada necessária; não usa conta padrão.')
    return uid


def _autor_valido(uid):
    if isinstance(uid,bool) or not isinstance(uid,int) or uid <= 0:
        raise ValueError('Identidade autenticada inválida.')
    return uid


def carregar_teses(*, user_id_fn=None, listar_fn=None):
    from database.db import listar_teses_macro
    uid = _autor_valido((user_id_fn or usuario_servidor)())
    return teses_do_usuario((listar_fn or listar_teses_macro)(),uid)


def salvar_tese(tese, *, user_id_fn=None, registrar_fn=None, listar_fn=None):
    """Só confirma persistência após leitura do próprio registro no servidor."""
    from database.db import registrar_decisao, listar_teses_macro
    uid = _autor_valido((user_id_fn or usuario_servidor)())
    r = validar_tese(tese)
    if r['autor_id'] != uid:
        raise ValueError('Autor diferente da sessão autenticada.')
    listar = listar_fn or listar_teses_macro
    existentes = teses_do_usuario(listar(),uid)
    anteriores = [t for t in existentes if t['id_tese'] == r['id_tese']]
    ultima = max((t['revisao'] for t in anteriores),default=0)
    if r['revisao'] == ultima and any(t == r for t in anteriores):
        # Retentativa após insert confirmado pelo servidor e readback interrompido.
        return r
    if r['revisao'] != ultima + 1:
        raise ValueError('Revisão desatualizada. Recarregue a tese antes de salvar.')
    (registrar_fn or registrar_decisao)('MACRO',TIPO,hoje_local().isoformat(),None,None,serializar_tese(r))
    confirmado = any(t == r for t in teses_do_usuario(listar(),uid))
    if not confirmado:
        raise RuntimeError('Gravação não confirmada no servidor; mantenha o rascunho e exporte uma cópia.')
    return r


def exportar_tese(tese):
    return json.dumps({'formato':'finterminal-tese-macro','versao':1,'tese':validar_tese(tese)},
                      ensure_ascii=False,allow_nan=False,indent=2)


def importar_tese(conteudo, autor_id):
    if isinstance(conteudo,bytes):
        conteudo = conteudo.decode('utf-8-sig')
    if not isinstance(conteudo,str) or len(conteudo) > 1000000:
        raise ValueError('Arquivo de tese inválido ou muito grande.')
    try:
        doc = json.loads(conteudo)
        if doc.get('formato') != 'finterminal-tese-macro' or doc.get('versao') != 1:
            raise ValueError('Formato de importação não suportado.')
        tese = validar_tese(doc['tese'])
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ValueError('Arquivo de tese incompatível ou inválido.') from None
    # Uma importação é uma cópia nova. Nunca sequestra a autoria/UUID de outra conta.
    tese.update(id_tese=str(uuid4()),autor_id=autor_id,revisao=1,criado_em=_agora(),revisado_em=_agora())
    return validar_tese(tese)


def alertas_tese(tese, contexto_atual=None, hoje=None):
    hoje = hoje or hoje_local()
    if tese['status'] in ('invalidada','encerrada'):
        return []
    alertas = []
    if date.fromisoformat(tese['revisar_em']) <= hoje:
        alertas.append('Revisão vencida' if date.fromisoformat(tese['revisar_em']) < hoje else 'Revisão prevista para hoje')
    atual = contexto_atual or {}
    for campo in ('quadrante','regime'):
        anterior = tese['contexto'].get(campo)
        if anterior and atual.get(campo) and anterior != atual[campo]:
            alertas.append(f'{campo.capitalize()} mudou desde o registro; confira a condição de invalidação.')
    return alertas


def eh_tese_macro(registro):
    return registro.get('tipo') == TIPO or str(registro.get('tese') or '').startswith(PREFIXO)
