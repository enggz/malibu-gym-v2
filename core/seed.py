"""DATA SINTETIS (bukan data Malibu Gym asli) untuk demo analisis. Akun sintetis tidak bisa login."""
import secrets
from datetime import datetime, timedelta
import numpy as np
from .db import conn
from .service import ts

FIRST = ["Budi", "Sari", "Andi", "Dewi", "Rudi", "Maya", "Agus", "Rina", "Joko", "Tina", "Eko", "Lia"]
LAST = ["Santoso", "Wijaya", "Putra", "Lestari", "Hidayat", "Saputra", "Utami", "Nugroho"]

def seed(n=150, rng_seed=42):
    rng = np.random.default_rng(rng_seed)
    now = datetime.now()
    w = np.full(24, 0.2); w[6:9] = 2; w[17:21] = 4; w[:5] = 0; w[22:] = 0.05
    w /= w.sum()
    with conn() as c:
        pid = c.execute("SELECT id,price FROM packages WHERE name='Bulanan'").fetchone()
        for i in range(n):
            join = now - timedelta(days=int(rng.integers(20, 200)))
            K = max(1, (now - join).days // 30)
            churner = K >= 2 and rng.random() < 0.35
            P = int(rng.integers(1, K)) if churner else K + 1
            end = join + timedelta(days=30 * P)
            base = max(2.0, rng.normal(12, 4))
            cur = c.execute("INSERT INTO users(name,email,salt,pw_hash,role,qr_token,active_until,is_synthetic,created_at) "
                            "VALUES(?,?,?,?,'member',?,?,1,?)",
                            (f"{rng.choice(FIRST)} {rng.choice(LAST)}", f"synthetic{secrets.token_hex(4)}@example.test",
                             "x", "x", secrets.token_urlsafe(16), ts(end), ts(join)))
            uid = cur.lastrowid
            for p in range(P):
                start = join + timedelta(days=30 * p)
                if start > now:
                    break
                c.execute("INSERT INTO transactions(user_id,package_id,amount,method,status,created_at,paid_at) VALUES(?,?,?,?,'paid',?,?)",
                          (uid, pid["id"], pid["price"], str(rng.choice(["Tunai", "QRIS", "EDC"])), ts(start), ts(start)))
                rate = base * (1 - 0.8 * (p + 1) / P) if churner else base
                for _ in range(int(rng.poisson(max(rate, 0.5)))):
                    t = start + timedelta(days=float(rng.uniform(0, 30)))
                    t = t.replace(hour=int(rng.choice(24, p=w)), minute=int(rng.integers(60)), second=0, microsecond=0)
                    if t <= now:
                        c.execute("INSERT INTO attendance(user_id,ts,result) VALUES(?,?,'GRANTED')", (uid, ts(t)))
    return n
