-- Histórico prospectivo append-only. NÃO reconstrói vintages de antes da coleta.
-- Executar manualmente uma vez; seguro executar novamente. Snapshot atual permanece.
CREATE TABLE IF NOT EXISTS public.macro_observations (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    observacao_hash text NOT NULL UNIQUE,
    serie_id text NOT NULL,
    referencia_em date NOT NULL,
    disponivel_em timestamptz NOT NULL,
    coletado_em timestamptz NOT NULL,
    valor double precision NOT NULL,
    fonte text NOT NULL,
    unidade text NOT NULL,
    disponibilidade_base text NOT NULL,
    vintage_base text NOT NULL DEFAULT 'observada_na_coleta'
);
CREATE INDEX IF NOT EXISTS macro_observations_known_idx
    ON public.macro_observations (serie_id, referencia_em, coletado_em DESC);
CREATE INDEX IF NOT EXISTS macro_observations_available_idx
    ON public.macro_observations (serie_id, disponivel_em, coletado_em);
ALTER TABLE public.macro_observations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS leitura_macro_observations ON public.macro_observations;
CREATE POLICY leitura_macro_observations ON public.macro_observations
    FOR SELECT TO anon, authenticated USING (true);
DROP POLICY IF EXISTS inserir_macro_observations ON public.macro_observations;
CREATE POLICY inserir_macro_observations ON public.macro_observations
    FOR INSERT TO service_role WITH CHECK (true);
GRANT SELECT ON public.macro_observations TO anon, authenticated;
GRANT SELECT, INSERT ON public.macro_observations TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.macro_observations_id_seq TO service_role;
REVOKE INSERT, UPDATE, DELETE ON public.macro_observations FROM anon, authenticated;
REVOKE UPDATE, DELETE ON public.macro_observations FROM service_role;
CREATE OR REPLACE FUNCTION public.bloquear_mutacao_macro_observations()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'macro_observations e append-only; registre uma nova versao';
END;
$$;
DROP TRIGGER IF EXISTS macro_observations_immutable ON public.macro_observations;
CREATE TRIGGER macro_observations_immutable
    BEFORE UPDATE OR DELETE ON public.macro_observations
    FOR EACH ROW EXECUTE FUNCTION public.bloquear_mutacao_macro_observations();
COMMENT ON TABLE public.macro_observations IS
    'Versoes observadas pelo terminal a partir da implantacao. as_of requer coleta e disponibilidade <= corte; atrasos assumidos nao equivalem a vintages ALFRED.';
