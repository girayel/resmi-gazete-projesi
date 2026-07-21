-- Sifre sifirlama linkleri icin tablo.
-- Calistirma: DBeaver'da SQL Editor'de ac, Alt+X ile calistir.

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id serial PRIMARY KEY,
    user_id integer NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token varchar(64) NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    used_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- user_id'ye gore sorgu atmiyoruz aslinda (token'a gore ariyoruz, token zaten
-- UNIQUE oldugu icin index'li) ama bir kullanicinin eski token'larini gormek
-- istersek diye yine de faydali.
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user_id ON password_reset_tokens(user_id);
