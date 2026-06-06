-- ============================================================
-- Migração: tabela macro_snapshots
-- Finalidade: persistir séries históricas macro (BCB + FRED)
--             para servir como fallback em fins de semana /
--             cold-start quando as APIs externas não respondem.
--
-- Executar 1x no Supabase → SQL Editor
-- ============================================================

CREATE TABLE IF NOT EXISTS public.macro_snapshots (
    origem       text        PRIMARY KEY,  -- 'bcb_br', 'fred_global', etc.
    payload      jsonb       NOT NULL,      -- DataFrame serializado (orient='split')
    n_linhas     integer,
    n_colunas    integer,
    data_inicio  date,
    data_fim     date,
    updated_at   timestamptz NOT NULL DEFAULT now()
);

-- Índice para consultas por data de atualização
CREATE INDEX IF NOT EXISTS idx_macro_snapshots_updated
    ON public.macro_snapshots (updated_at DESC);

-- Row Level Security: leitura pública (anon key), escrita apenas service_role
ALTER TABLE public.macro_snapshots ENABLE ROW LEVEL SECURITY;

-- Política: qualquer usuário autenticado ou anon pode ler
CREATE POLICY "leitura_publica" ON public.macro_snapshots
    FOR SELECT USING (true);

-- Política: apenas service_role pode escrever
-- (o sync_macro.py usa SUPABASE_SERVICE_KEY — essa política garante isso)
CREATE POLICY "escrita_service_role" ON public.macro_snapshots
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Comentários de documentação
COMMENT ON TABLE  public.macro_snapshots IS
    'Cache de séries históricas macro (BCB + FRED). '
    'Atualizado via sync_macro.py nos dias úteis. '
    'Fallback quando APIs externas falham (fins de semana, manutenção).';

COMMENT ON COLUMN public.macro_snapshots.origem IS
    'Identificador da série: bcb_br | fred_global | yfinance_macro';

COMMENT ON COLUMN public.macro_snapshots.payload IS
    'DataFrame serializado com pd.DataFrame.to_json(orient="split"). '
    'Reconstruir com pd.read_json(payload, orient="split", convert_dates=True).';
