-- Kullaniciyi pasif/aktif yapabilmek icin. Pasif kullanici login olamaz.
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;