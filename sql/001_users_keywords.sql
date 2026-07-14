-- Kullanici hesaplari ve anahtar kelime (keyword) bildirim sistemi icin sema.
-- Calistirma: psql -h localhost -U postgres -d gazette_db -f sql/001_users_keywords.sql
-- (ya da pgAdmin/DBeaver ile ayni dosyayi Query Tool'da acip calistirabilirsin.)

-- 1) Kullanicilar. role kolonu simdilik 'admin' / 'user' olmak uzere iki deger alir.
CREATE TABLE IF NOT EXISTS users (
    id serial PRIMARY KEY,
    email varchar(255) NOT NULL UNIQUE,
    password_hash varchar(255) NOT NULL,
    role varchar(20) NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    created_at timestamptz NOT NULL DEFAULT now()
);

-- 2) Anahtar kelime havuzu. Kullanicilar sadece bu havuzdan secim yapar;
-- havuza yeni kelime eklemek admin islemi olacak (ileride /api/keywords POST admin-only).
CREATE TABLE IF NOT EXISTS keywords (
    id serial PRIMARY KEY,
    keyword varchar(100) NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- 3) Kullanici <-> keyword eslesmesi (many-to-many).
-- added_by_user_id: NULL ise kullanici kendisi eklemistir, doluysa bir admin
-- baska bir kullanici adina bu kelimeyi eklemistir.
CREATE TABLE IF NOT EXISTS user_keywords (
    id serial PRIMARY KEY,
    user_id integer NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    keyword_id integer NOT NULL REFERENCES keywords(id) ON DELETE CASCADE,
    added_by_user_id integer REFERENCES users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, keyword_id)
);

-- Postgres foreign key kolonlarini otomatik indexlemez; sorgularda
-- (WHERE user_id = ...) ve (WHERE keyword_id = ...) sik kullanilacagi icin
-- ikisini de ayri ayri indexliyoruz (UNIQUE(user_id, keyword_id) sadece
-- user_id'yi soldan kapsar, keyword_id icin ayri index gerekir).
CREATE INDEX IF NOT EXISTS idx_user_keywords_user_id ON user_keywords(user_id);
CREATE INDEX IF NOT EXISTS idx_user_keywords_keyword_id ON user_keywords(keyword_id);

-- Baslangic keyword havuzu (Resmi Gazete baglaminda sik aranan terimler).
-- Kullanicilar bunlardan istediklerini secebilecek; admin daha sonra
-- POST /api/keywords ile yenilerini ekleyebilecek.
INSERT INTO keywords (keyword) VALUES
    ('ihale'),
    ('vergi'),
    ('yönetmelik değişikliği'),
    ('kanun'),
    ('kanun hükmünde kararname'),
    ('cumhurbaşkanlığı kararnamesi'),
    ('genelge'),
    ('tebliğ'),
    ('yönetmelik'),
    ('teşvik'),
    ('kamu ihalesi'),
    ('gümrük'),
    ('sosyal güvenlik'),
    ('asgari ücret'),
    ('imar'),
    ('çevre'),
    ('enerji'),
    ('sağlık'),
    ('eğitim'),
    ('ceza'),
    ('af'),
    ('zam'),
    ('ihracat'),
    ('ithalat'),
    ('KDV'),
    ('SGK'),
    ('emeklilik'),
    ('personel alımı'),
    ('kadro'),
    ('atama'),
    ('disiplin yönetmeliği'),
    ('yatırım teşviki')
ON CONFLICT (keyword) DO NOTHING;
