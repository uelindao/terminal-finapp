-- ════════════════════════════════════════════════════════════════════════════
-- Migration 009 — ai_analyses cache
-- ════════════════════════════════════════════════════════════════════════════
-- Cache de análises geradas por IA para reuso entre sessões.
-- Evita gastar tokens (DeepSeek V4 Pro: $0.435/M input) quando a análise
-- já está fresca e os inputs (health score, fundamentos) não mudaram.
--
-- Política de cache por tipo:
--   research:   TTL 7 dias OR mudança de health score > 10pts
--   discovery:  TTL 1 dia
--   portfolio:  TTL 1 dia, por user_id
--
-- Aplicar manualmente no Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS ai_analyses (
    id                    uuid        DEFAULT gen_random_uuid() PRIMARY KEY,
    tipo                  text        NOT NULL,
    ticker                text,                                            -- NULL para análises não-ticker (discovery/portfolio)
    user_id               integer,                                         -- NULL = global (research é compartilhada entre todos)
    modo                  text,                                            -- subtipo (discovery: entrada/dividendo/realizacao; portfolio: performance/stress/etc)
    modelo                text,                                            -- deepseek-chat, gemini-2.5-flash, etc.
    conteudo              text        NOT NULL,                            -- texto da análise
    contexto_hash         text,                                            -- hash(prompt_inputs) — invalida se mudar
    health_score_snapshot integer,                                         -- score na hora da geração (para invalidação por threshold)
    created_at            timestamptz DEFAULT now(),
    expires_at            timestamptz NOT NULL
);

-- Lookup principal: por (tipo, ticker, user_id, modo)
CREATE INDEX IF NOT EXISTS ix_ai_analyses_lookup
    ON ai_analyses (tipo, ticker, user_id, modo, expires_at DESC);

-- Cleanup de expirados (rodar periodicamente)
CREATE INDEX IF NOT EXISTS ix_ai_analyses_expires
    ON ai_analyses (expires_at);

-- Lookup de histórico por ticker
CREATE INDEX IF NOT EXISTS ix_ai_analyses_ticker
    ON ai_analyses (ticker, created_at DESC);

COMMENT ON TABLE  ai_analyses                       IS 'Cache de análises IA para reuso e economia de tokens';
COMMENT ON COLUMN ai_analyses.tipo                  IS 'research | discovery | portfolio | tese | macro';
COMMENT ON COLUMN ai_analyses.modo                  IS 'subtipo opcional (ex.: discovery: entrada/dividendo/realizacao)';
COMMENT ON COLUMN ai_analyses.user_id               IS 'NULL = análise global compartilhada (research). preenchido = privada (portfolio)';
COMMENT ON COLUMN ai_analyses.contexto_hash         IS 'sha1 dos inputs estáticos do prompt; se mudar, força regeneração';
COMMENT ON COLUMN ai_analyses.health_score_snapshot IS 'health score na geração — invalida se delta > 10pts';
