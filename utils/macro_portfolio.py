"""Exposições qualitativas e cenários condicionais, sem betas estimados."""
from __future__ import annotations
from math import isfinite
from utils.setores import normalizar_setor

FATORES = ('juros_duration', 'crescimento', 'credito', 'commodities')
NIVEIS = ('alta', 'média', 'baixa', 'mista', 'a confirmar')
PERFIS_CLASSES = {
 'caixa':('baixa','baixa','mista','baixa'),
 'renda fixa prefixada':('alta','baixa','mista','baixa'),
 'renda fixa inflação':('alta','baixa','mista','baixa'),
 'pós-fixado':('baixa','baixa','mista','baixa'),
 'fii':('alta','média','alta','baixa'),
 'commodity':('baixa','média','baixa','alta'),
}
PERFIS_SETORIAIS = {
 'financeiro': ('mista','alta','alta','baixa'), 'consumo_ciclico': ('alta','alta','alta','mista'),
 'consumo_defensivo': ('baixa','baixa','média','média'), 'tecnologia': ('alta','alta','média','baixa'),
 'industria': ('média','alta','média','média'), 'imobiliario': ('alta','média','alta','baixa'),
 'utilities': ('alta','baixa','média','média'), 'energia': ('média','média','média','alta'),
 'materiais': ('média','alta','média','alta'), 'saude': ('média','baixa','média','baixa'),
 'comunicacao': ('média','média','média','baixa'),
}


def numero(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        v = float(v)
        return v if isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _primeiro(d, chaves):
    for chave in chaves:
        v = numero(d.get(chave))
        if v is not None and v > 0:
            return v
    return None


def _moeda(d):
    for chave in ('moeda', 'currency'):
        valor = str(d.get(chave) or '').strip().upper()
        if len(valor) == 3 and valor.isalpha():
            return valor
    return None


def montar_exposicoes(posicoes, precos_cache=None, fundamentos=None, cambios=None, ajustes=None):
    """Valor long em BRL; moeda/câmbio desconhecidos não entram na base modelada."""
    precos_cache, fundamentos, cambios, ajustes = precos_cache or {}, fundamentos or {}, cambios or {}, ajustes or {}
    if isinstance(posicoes, dict):
        posicoes = [{'ticker': tk, **dados} for tk, dados in posicoes.items()]
    itens = []
    for pos in posicoes or []:
        ticker = str(pos.get('ticker') or '').strip().upper()
        qtd = numero(pos.get('quantidade'))
        if not ticker or qtd is None or qtd <= 0:
            continue
        base = str(pos.get('ticker_base') or ticker).upper()
        pc, fund = precos_cache.get(base) or precos_cache.get(ticker) or {}, fundamentos.get(base) or fundamentos.get(ticker) or {}
        ajuste = ajustes.get(ticker) or {}
        moeda = _moeda(ajuste) or _moeda(pc) or _moeda(fund) or _moeda(pos)
        origem_moeda = 'informada' if moeda else 'ausente'
        if moeda is None and base.endswith('.SA'):
            moeda, origem_moeda = 'BRL', 'inferida da listagem B3'
        setor = normalizar_setor(ajuste.get('setor') or fund.get('setor') or '')
        classe = str(ajuste.get('classe') or fund.get('classe') or pos.get('classe') or 'a confirmar')
        preco = _primeiro(pc, ('preco', 'preco_atual', 'price', 'close'))
        fonte = 'cotação em cache' if preco is not None else 'ausente'
        if preco is None:
            preco = _primeiro(pos, ('preco_medio',))
            if preco is not None:
                fonte = 'custo da posição (fallback explícito)'
        valor_local = qtd * preco if preco is not None else None
        cambio = 1.0 if moeda == 'BRL' else numero(cambios.get(moeda))
        if cambio is not None and cambio <= 0:
            cambio = None
        valor_brl = valor_local * cambio if valor_local is not None and cambio is not None else None
        perfil = PERFIS_CLASSES.get(classe.lower()) or PERFIS_SETORIAIS.get(setor, ('a confirmar',) * 4)
        fatores = {f: ajuste.get(f) if ajuste.get(f) in NIVEIS else perfil[i] for i, f in enumerate(FATORES)}
        itens.append({'ticker':ticker, 'ticker_base':base, 'quantidade':qtd, 'setor':setor or 'a confirmar',
          'classe':classe, 'moeda':moeda or 'a confirmar', 'origem_moeda':origem_moeda, 'preco':preco,
          'base_valor':fonte, 'referencia_preco':pc.get('atualizado_em') or pc.get('updated_at'),
          'valor_local':valor_local, 'cambio_brl':cambio, 'valor_brl':valor_brl,
          'fx_direto':moeda or 'a confirmar', **fatores})
    total = sum(p['valor_brl'] for p in itens if p['valor_brl'] is not None)
    for p in itens:
        p['peso_pct'] = p['valor_brl'] / total * 100 if p['valor_brl'] is not None and total > 0 else None
    return {'posicoes':itens, 'valor_base_brl':total, 'n_posicoes':len(itens),
      'n_valoradas':sum(p['valor_brl'] is not None for p in itens),
      'n_custo':sum(p['base_valor'].startswith('custo') for p in itens),
      'cobertura_posicoes_pct':sum(p['valor_brl'] is not None for p in itens) / len(itens)*100 if itens else 0,
      'total_completo':bool(itens and all(p['valor_brl'] is not None for p in itens))}


def resumo_exposicoes(exposicoes):
    rows = []
    for fator in FATORES:
        for nivel in NIVEIS:
            valor = sum(p['valor_brl'] or 0 for p in exposicoes['posicoes'] if p[fator] == nivel)
            total = exposicoes['valor_base_brl']
            rows.append({'fator':fator, 'nivel':nivel, 'valor_brl':valor,
                         'peso_pct':valor / total*100 if total else None})
    return rows


def simular_cenario(exposicoes, choques_posicao=None, choques_fx=None):
    """Choques assumidos de preço e câmbio; composição multiplicativa exata."""
    choques_posicao, choques_fx = choques_posicao or {}, choques_fx or {}
    rows = []
    for p in exposicoes['posicoes']:
        local = numero(choques_posicao.get(p['ticker'], 0))
        fx = 0.0 if p['moeda'] == 'BRL' else numero(choques_fx.get(p['moeda'], 0))
        if local is None or fx is None or local < -100 or fx < -100:
            raise ValueError('Choques devem ser finitos e iguais ou superiores a −100%.')
        impacto = ((1 + local/100)*(1 + fx/100) - 1)*100
        base = p['valor_brl']
        delta = base*impacto/100 if base is not None else None
        rows.append({**p, 'choque_local_pct':local, 'choque_fx_pct':fx,
          'impacto_pct':impacto if base is not None else None, 'delta_brl':delta,
          'valor_cenario_brl':base + delta if base is not None else None})
    base = exposicoes['valor_base_brl']
    delta = sum(p['delta_brl'] for p in rows if p['delta_brl'] is not None)
    return {'posicoes':rows, 'valor_base_brl':base, 'delta_brl':delta,
      'impacto_pct':delta/base*100 if base > 0 else None, 'valor_cenario_brl':base + delta,
      'total_completo':exposicoes['total_completo'], 'cobertura_posicoes_pct':exposicoes['cobertura_posicoes_pct']}
