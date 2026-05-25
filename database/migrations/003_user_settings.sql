-- =============================================================================
-- FinTerminal — Migration 003: configurações pessoais por usuário
-- Execute no Supabase Dashboard → SQL Editor
-- Idempotente: usa IF NOT EXISTS
-- =============================================================================

CREATE TABLE IF NOT EXISTS user_settings (
    id              BIGSERIAL    PRIMARY KEY,
    user_id         INTEGER      NOT NULL UNIQUE,
    ai_provider     TEXT         DEFAULT 'deepseek',
    ai_api_key_enc  TEXT,                          -- chave criptografada com Fernet
    ai_model        TEXT         DEFAULT 'deepseek-chat',
    moeda_base      TEXT         DEFAULT 'BRL',
    benchmark       TEXT         DEFAULT 'IBOV',
    alert_threshold INTEGER      DEFAULT 40,
    created_at      TIMESTAMPTZ  DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_settings_user
    ON user_settings(user_id);

CREATE OR REPLACE TRIGGER trg_user_settings_updated_at
    BEFORE UPDATE ON user_settings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
