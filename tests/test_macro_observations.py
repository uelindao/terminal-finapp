import json
from types import SimpleNamespace
import pandas as pd
import pytest
from utils import macro_supabase as m


class Query:
    def __init__(self, client, table):
        self.client, self.table = client, table
        self.filters, self.orderings, self.bounds, self.count, self.mutation = [], [], None, None, None
    def select(self, *args, **kwargs): return self
    def eq(self, col, value): self.filters.append((col, "eq", value)); return self
    def gte(self, col, value): self.filters.append((col, "gte", value)); return self
    def lte(self, col, value): self.filters.append((col, "lte", value)); return self
    def order(self, col, desc=False): self.orderings.append((col, desc)); return self
    def limit(self, count): self.count = count; return self
    def range(self, start, end): self.bounds = (start, end); return self
    def upsert(self, payload, **kwargs): self.mutation = payload; return self
    def execute(self):
        if self.table == "macro_observations" and not self.client.table_exists:
            raise RuntimeError("table absent")
        if self.table == "macro_snapshots" and self.client.fallback_failure:
            raise RuntimeError("offline")
        rows = self.client.tables.setdefault(self.table, [])
        if self.mutation is not None:
            if self.table == "macro_snapshots":
                old = next((r for r in rows if r["origem"] == self.mutation["origem"]), None)
                if old: old.update(self.mutation)
                else: rows.append(dict(self.mutation))
            else:
                rows.extend(self.mutation)
            return SimpleNamespace(data=[])
        data = list(rows)
        for col, op, value in self.filters:
            data = [r for r in data if (str(r[col]) == str(value) if op == "eq" else str(r[col]) >= str(value) if op == "gte" else str(r[col]) <= str(value))]
        for col, desc in reversed(self.orderings): data.sort(key=lambda r: r[col], reverse=desc)
        if self.bounds: data = data[self.bounds[0]:self.bounds[1]+1]
        if self.count is not None: data = data[:self.count]
        return SimpleNamespace(data=data)


class Client:
    def __init__(self, table_exists=False):
        self.table_exists, self.fallback_failure = table_exists, False
        self.tables = {}
    def table(self, table): return Query(self, table)


def salvar(client, value, coleta):
    return m.salvar_observacoes_versionadas("x", pd.Series([value], index=pd.to_datetime(["2020-01-01"])),
        fonte="teste", unidade="%", atraso_dias=20, mes_fechado=True, coletado_em=coleta, cliente=client)


@pytest.mark.parametrize("table_exists", [False, True])
def test_versoes_asof_conhecidas_sem_antecipar_backfill(table_exists):
    c = Client(table_exists)
    assert salvar(c, 1., "2026-01-01")["n"] == 1
    assert salvar(c, 1., "2026-01-02")["n"] == 0
    assert salvar(c, 2., "2026-02-01")["n"] == 1
    assert m.carregar_observacoes_versionadas("x", as_of="2025-01-01", cliente=c).empty
    antigo = m.carregar_observacoes_versionadas("x", as_of="2026-01-15", cliente=c)
    assert antigo["valor"].tolist() == [1.]
    assert m.carregar_observacoes_versionadas("x", cliente=c)["valor"].tolist() == [2.]
    todas = m.carregar_observacoes_versionadas("x", cliente=c, todas_versoes=True)
    assert todas["valor"].tolist() == [1., 2.]
    assert str(todas["coletado_em"].dt.tz) == "UTC"


def test_disponibilidade_tambem_restringe_asof():
    rows = m.preparar_observacoes_versionadas("x", pd.Series([1.], index=pd.to_datetime(["2026-01-01"])),
        fonte="teste", unidade="%", coletado_em="2026-01-02", mes_fechado=True, atraso_dias=20)
    assert m.selecionar_observacoes_conhecidas(rows, as_of="2026-02-10").empty
    assert len(m.selecionar_observacoes_conhecidas(rows, as_of="2026-02-21")) == 1


def test_leitura_falha_nao_sobrescreve_fallback():
    c = Client()
    salvar(c, 1., "2026-01-01")
    antes = json.dumps(c.tables)
    c.fallback_failure = True
    assert not salvar(c, 2., "2026-02-01")["ok"]
    assert json.dumps(c.tables) == antes


def test_migration_posterior_preserva_fallback():
    c = Client()
    salvar(c, 1., "2026-01-01")
    c.table_exists = True
    assert salvar(c, 1., "2026-01-02")["n"] == 0
    assert salvar(c, 2., "2026-02-01")["armazenamento"] == "versionado"
    assert m.carregar_observacoes_versionadas("x", as_of="2026-01-15", cliente=c)["valor"].tolist() == [1.]
    assert m.carregar_observacoes_versionadas("x", cliente=c, todas_versoes=True)["valor"].tolist() == [1., 2.]


def test_snapshot_marca_coleta_verdadeira_e_stringio(monkeypatch):
    c = Client()
    df = pd.DataFrame({"x": [1.]}, index=pd.to_datetime(["2026-01-01"]))
    c.tables["macro_snapshots"] = [{"origem": "fonte", "payload": m._df_to_json(df),
        "updated_at": "2026-10-05T03:00:00+00:00", "n_linhas": 1}]
    monkeypatch.setattr(m, "_sb", lambda: c)
    result = m.carregar_snapshot("fonte", max_age_days=3650)
    assert result.attrs["coletado_em"] == "2026-10-05T03:00:00+00:00"
    assert result.iloc[0, 0] == 1.


def test_coleta_observada_igual_nao_cria_revisao_diaria():
    c = Client()
    serie = pd.Series([4.], index=pd.to_datetime(["2026-01-01"]))
    args = dict(fonte="Focus", unidade="%", disponibilidade_base="observada_na_coleta", cliente=c)
    assert m.salvar_observacoes_versionadas("focus", serie, coletado_em="2026-01-02", **args)["n"] == 1
    assert m.salvar_observacoes_versionadas("focus", serie, coletado_em="2026-01-03", **args)["n"] == 0
    assert m.carregar_observacoes_versionadas("focus", cliente=c).iloc[0]["coletado_em"] == pd.Timestamp("2026-01-02", tz="UTC")


def test_indice_pequeno_evitar_releitura_historico_sem_mudancas(monkeypatch):
    c = Client()
    salvar(c, 1., "2026-01-01")
    def proibida(*a, **k):
        raise AssertionError("não deve reler payload de vintages sem alterações")
    monkeypatch.setattr(m, "carregar_observacoes_versionadas", proibida)
    assert salvar(c, 1., "2026-01-02")["n"] == 0
