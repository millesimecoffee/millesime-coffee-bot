-- =====================================================================
--  Schéma Supabase pour le bot Millésime Coffee
--  À exécuter UNE FOIS dans Supabase → SQL Editor → New query → Run
-- =====================================================================

-- ── Commandes ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
    id         TEXT PRIMARY KEY,
    user_id    BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    data       JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_orders_user_id      ON orders (user_id);
CREATE INDEX IF NOT EXISTS idx_orders_created_at   ON orders (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_user_created ON orders (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_data_gin     ON orders USING GIN (data jsonb_path_ops);

-- ── Blacklist (bans permanents) ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS blacklist (
    user_id    BIGINT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Blocked (anti-spam temporaire) ───────────────────────────────────
CREATE TABLE IF NOT EXISTS blocked (
    user_id    BIGINT PRIMARY KEY,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_blocked_expires_at ON blocked (expires_at);

-- ── RLS : désactivé (la clé service_role passe outre de toute façon)
ALTER TABLE orders    DISABLE ROW LEVEL SECURITY;
ALTER TABLE blacklist DISABLE ROW LEVEL SECURITY;
ALTER TABLE blocked   DISABLE ROW LEVEL SECURITY;

-- ── Vérification ─────────────────────────────────────────────────────
SELECT 'orders'    AS tbl, COUNT(*) FROM orders
UNION ALL SELECT 'blacklist', COUNT(*) FROM blacklist
UNION ALL SELECT 'blocked',   COUNT(*) FROM blocked;
