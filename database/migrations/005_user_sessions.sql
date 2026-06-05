-- Sessões persistentes de autenticação (cross-tab login)
-- Executar no Supabase Dashboard → SQL Editor

CREATE TABLE IF NOT EXISTS user_sessions (
    id          BIGSERIAL PRIMARY KEY,
    token       TEXT        NOT NULL UNIQUE,
    user_id     BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_token     ON user_sessions(token);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id   ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_expires   ON user_sessions(expires_at);

-- Remove sessões expiradas automaticamente (requer pg_cron ou chamada manual)
-- Alternativa: a aplicação filtra expires_at > now() em toda consulta
