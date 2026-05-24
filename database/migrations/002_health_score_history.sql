-- Migration 002: histórico temporal do health score por ativo
-- Execute no Supabase Dashboard → SQL Editor

CREATE TABLE IF NOT EXISTS health_score_history (
    id           BIGSERIAL    PRIMARY KEY,
    ticker       TEXT         NOT NULL,
    score        INTEGER      NOT NULL CHECK (score BETWEEN 0 AND 100),
    calculado_em TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Índice composto para buscas por ativo ordenadas por data (desc)
CREATE INDEX IF NOT EXISTS idx_hsh_ticker_calculado_em
    ON health_score_history (ticker, calculado_em DESC);
