-- =============================================================================
-- FinTerminal — Cache para Fear & Greed Index (EUA + BR)
-- Execute este arquivo no Supabase Dashboard → SQL Editor
-- =============================================================================

CREATE TABLE IF NOT EXISTS fear_greed_cache (
    market       TEXT PRIMARY KEY,          -- 'us' ou 'br'
    score        INTEGER NOT NULL,          -- 0-100
    label        TEXT NOT NULL,             -- ex: 'GANÂNCIA', 'MEDO'
    componentes  JSONB DEFAULT '{}',        -- breakdown dos componentes
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

-- RLS: leitura pública, escrita autenticada
ALTER TABLE fear_greed_cache ENABLE ROW LEVEL SECURITY;

CREATE POLICY "fear_greed_leitura_publica" ON fear_greed_cache
    FOR SELECT USING (true);

CREATE POLICY "fear_greed_escrita_autenticada" ON fear_greed_cache
    FOR INSERT WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "fear_greed_update_autenticado" ON fear_greed_cache
    FOR UPDATE USING (auth.role() = 'authenticated');

-- Trigger para updated_at
CREATE TRIGGER fear_greed_cache_updated_at
    BEFORE UPDATE ON fear_greed_cache
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- =============================================================================
-- Commodities: reutiliza macro_snapshots com origem='commodities_yf'
-- (não precisa de tabela separada — já existe)
-- =============================================================================
