import os, sqlite3, hashlib, secrets
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv; load_dotenv(ROOT / ".env")  # variabel lingkungan yang sudah ada tidak ditimpa
except ImportError:
    pass

_db = os.getenv("DB_PATH", "malibu.db")
DB_PATH = _db if os.path.isabs(_db) else str(ROOT / _db)  # relatif -> di root proyek, bukan folder kerja
FOREVER = "2099-12-31 23:59:59"  # masa aktif admin: tidak pernah kedaluwarsa
SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
  salt TEXT NOT NULL, pw_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('member','admin')),
  qr_token TEXT UNIQUE, active_until TEXT, is_synthetic INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS packages(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, days INTEGER NOT NULL CHECK(days>0),
  price INTEGER NOT NULL CHECK(price>=0));
CREATE TABLE IF NOT EXISTS transactions(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
  package_id INTEGER NOT NULL REFERENCES packages(id), amount INTEGER NOT NULL,
  method TEXT NOT NULL CHECK(method IN ('Tunai','QRIS','EDC')),
  status TEXT NOT NULL CHECK(status IN ('pending','paid')),
  created_at TEXT NOT NULL, paid_at TEXT);
CREATE TABLE IF NOT EXISTS attendance(
  id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), ts TEXT NOT NULL,
  result TEXT NOT NULL CHECK(result IN ('GRANTED','DENIED')), reason TEXT);
CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY, ts TEXT NOT NULL, message TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notifications(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
  message TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_att_ts ON attendance(ts);
CREATE INDEX IF NOT EXISTS ix_att_user ON attendance(user_id);
CREATE INDEX IF NOT EXISTS ix_tx_status ON transactions(status);
"""
PACKAGES = [("Harian", 1, 25000), ("Bulanan", 30, 150000), ("Triwulan", 90, 400000), ("Tahunan", 365, 1400000)]

def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(8)
    return salt, hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100_000).hex()

@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()

def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def upsert_admin(c, email, pw):
    """Buat admin baru, atau jadikan akun ber-email sama sebagai admin dengan password ini.
    Password lama akun itu ditimpa, jadi akun yang sempat didaftarkan orang lain tidak bisa dipakai."""
    email = email.strip().lower()
    salt, h = hash_pw(pw)
    if c.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        c.execute("UPDATE users SET role='admin', salt=?, pw_hash=? WHERE email=?", (salt, h, email))
    else:
        c.execute("INSERT INTO users(name,email,salt,pw_hash,role,created_at) VALUES('Admin',?,?,?,'admin',?)",
                  (email, salt, h, _now()))

def grant_admin_access(c):
    """Semua admin selalu punya masa aktif tanpa batas dan QR akses (idempotent)."""
    for r in c.execute("SELECT id, qr_token FROM users WHERE role='admin'").fetchall():
        c.execute("UPDATE users SET active_until=?, qr_token=? WHERE id=?",
                  (FOREVER, r["qr_token"] or secrets.token_urlsafe(16), r["id"]))

def admin_exists():
    with conn() as c:
        return c.execute("SELECT 1 FROM users WHERE role='admin'").fetchone() is not None

def init():
    with conn() as c:
        c.executescript(SCHEMA)
        if not c.execute("SELECT 1 FROM packages").fetchone():
            c.executemany("INSERT INTO packages(name,days,price) VALUES(?,?,?)", PACKAGES)
        email, pw = (os.getenv("ADMIN_EMAIL") or "").strip(), os.getenv("ADMIN_PASSWORD") or ""
        if email and pw:
            row = c.execute("SELECT role FROM users WHERE email=?", (email.lower(),)).fetchone()
            if not row or row["role"] != "admin":
                upsert_admin(c, email, pw)
        grant_admin_access(c)
