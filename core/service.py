import io, re, secrets, sqlite3
from datetime import datetime, timedelta
import qrcode
from .db import FOREVER, conn, hash_pw

FMT = "%Y-%m-%d %H:%M:%S"
METHODS = ("Tunai", "QRIS", "EDC")
DUP_WINDOW = timedelta(minutes=10)

def now(): return datetime.now()
def ts(d): return d.strftime(FMT)
def parse(s): return datetime.strptime(s, FMT)

def register(name, email, pw):
    email = email.strip().lower()
    if not name.strip() or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("Nama atau email tidak valid")
    if len(pw) < 8:
        raise ValueError("Password minimal 8 karakter")
    salt, h = hash_pw(pw)
    try:
        with conn() as c:
            cur = c.execute("INSERT INTO users(name,email,salt,pw_hash,role,created_at) VALUES(?,?,?,?,'member',?)",
                            (name.strip(), email, salt, h, ts(now())))
        return cur.lastrowid
    except sqlite3.IntegrityError:
        raise ValueError("Email sudah terdaftar")

def login(email, pw):
    with conn() as c:
        u = c.execute("SELECT * FROM users WHERE email=?", (email.strip().lower(),)).fetchone()
    if u and u["pw_hash"] == hash_pw(pw, u["salt"])[1]:
        return dict(u)
    return None

def get_user(uid):
    with conn() as c:
        r = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    return dict(r) if r else None

def packages():
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM packages ORDER BY days")]

def create_order(uid, package_id, method):
    if method not in METHODS:
        raise ValueError("Metode pembayaran tidak valid")
    with conn() as c:
        p = c.execute("SELECT * FROM packages WHERE id=?", (package_id,)).fetchone()
        if not p:
            raise ValueError("Paket tidak ditemukan")
        cur = c.execute("INSERT INTO transactions(user_id,package_id,amount,method,status,created_at) VALUES(?,?,?,?,'pending',?)",
                        (uid, package_id, p["price"], method, ts(now())))
    return cur.lastrowid

def pending_orders():
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT t.id,u.name,p.name AS paket,t.amount,t.method,t.created_at FROM transactions t "
            "JOIN users u ON u.id=t.user_id JOIN packages p ON p.id=t.package_id "
            "WHERE t.status='pending' ORDER BY t.id")]

def my_orders(uid):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT t.id,p.name AS paket,t.amount,t.method,t.status,t.created_at FROM transactions t "
            "JOIN packages p ON p.id=t.package_id WHERE t.user_id=? ORDER BY t.id DESC", (uid,))]

def confirm_payment(tx_id, at=None):
    at = at or now()
    with conn() as c:
        t = c.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()
        if not t or t["status"] != "pending":
            raise ValueError("Transaksi tidak ditemukan atau sudah dikonfirmasi")
        days = c.execute("SELECT days FROM packages WHERE id=?", (t["package_id"],)).fetchone()["days"]
        u = c.execute("SELECT active_until FROM users WHERE id=?", (t["user_id"],)).fetchone()
        start = max(at, parse(u["active_until"])) if u["active_until"] else at
        new_end = ts(start + timedelta(days=days))
        c.execute("UPDATE users SET active_until=?, qr_token=COALESCE(qr_token,?) WHERE id=?",
                  (new_end, secrets.token_urlsafe(16), t["user_id"]))
        c.execute("UPDATE transactions SET status='paid', paid_at=? WHERE id=?", (ts(at), tx_id))
    return new_end

def qr_png(token):
    buf = io.BytesIO()
    qrcode.make(token).save(buf, format="PNG")
    return buf.getvalue()

def decode_qr(img_bytes):
    import cv2, numpy as np
    img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    val, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
    return val

def _log(c, uid, at, result, reason, alert=None):
    c.execute("INSERT INTO attendance(user_id,ts,result,reason) VALUES(?,?,?,?)", (uid, ts(at), result, reason))
    if alert:
        c.execute("INSERT INTO alerts(ts,message) VALUES(?,?)", (ts(at), alert))

def scan(token, at=None):
    """Smart Access Gate (simulasi). Return (diizinkan, pesan)."""
    at = at or now()
    token = (token or "").strip()
    with conn() as c:
        u = c.execute("SELECT * FROM users WHERE qr_token=?", (token,)).fetchone() if token else None
        if not u:
            _log(c, None, at, "DENIED", "QR tidak dikenal", "QR tidak valid dipindai di gate")
            return False, "QR tidak valid"
        if u["role"] == "admin":  # admin: akses mutlak, tanpa cek masa aktif / scan ganda
            _log(c, u["id"], at, "GRANTED", "Admin")
            return True, f"Silakan masuk, {u['name']} (admin)"
        if not u["active_until"] or parse(u["active_until"]) < at:
            _log(c, u["id"], at, "DENIED", "Masa aktif habis", f"Member {u['name']} memakai QR kedaluwarsa")
            return False, "Masa aktif habis"
        last = c.execute("SELECT ts FROM attendance WHERE user_id=? AND result='GRANTED' ORDER BY ts DESC LIMIT 1",
                         (u["id"],)).fetchone()
        if last and at - parse(last["ts"]) < DUP_WINDOW:
            _log(c, u["id"], at, "DENIED", "Scan ganda",
                 f"Indikasi QR dipakai bergantian: {u['name']} scan ulang < 10 menit")
            return False, "Scan ganda terdeteksi"
        _log(c, u["id"], at, "GRANTED", None)
        return True, f"Silakan masuk, {u['name']}"

def alerts(limit=50):
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT ts,message FROM alerts ORDER BY id DESC LIMIT ?", (limit,))]

def notify(user_ids, message):
    with conn() as c:
        c.executemany("INSERT INTO notifications(user_id,message,created_at) VALUES(?,?,?)",
                      [(int(i), message, ts(now())) for i in user_ids])

def notifications(uid):
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT message,created_at FROM notifications WHERE user_id=? ORDER BY id DESC", (uid,))]


# ---- Manajemen akun (khusus admin; peran dicek di sini, bukan hanya di UI) ----
def _require_admin(c, actor_id):
    a = c.execute("SELECT role FROM users WHERE id=?", (actor_id,)).fetchone()
    if not a or a["role"] != "admin":
        raise PermissionError("Hanya admin yang boleh melakukan ini")

def list_users(actor_id):
    with conn() as c:
        _require_admin(c, actor_id)
        return [dict(r) for r in c.execute(
            "SELECT id,name,email,role,active_until,created_at FROM users WHERE is_synthetic=0 ORDER BY id")]

def set_role(actor_id, target_id, role):
    if role not in ("member", "admin"):
        raise ValueError("Peran tidak valid")
    with conn() as c:
        _require_admin(c, actor_id)
        if actor_id == target_id:
            raise ValueError("Tidak bisa mengubah peran akun sendiri")
        t = c.execute("SELECT role,active_until FROM users WHERE id=?", (target_id,)).fetchone()
        if not t:
            raise ValueError("Akun tidak ditemukan")
        if role == "admin":
            c.execute("UPDATE users SET role='admin', active_until=?, qr_token=COALESCE(qr_token,?) WHERE id=?",
                      (FOREVER, secrets.token_urlsafe(16), target_id))
        else:  # diturunkan jadi member: cabut masa aktif tanpa batas
            c.execute("UPDATE users SET role='member', active_until=? WHERE id=?",
                      (None if t["active_until"] == FOREVER else t["active_until"], target_id))

def reset_password(actor_id, target_id, new_pw):
    if len(new_pw) < 8:
        raise ValueError("Password minimal 8 karakter")
    salt, h = hash_pw(new_pw)
    with conn() as c:
        _require_admin(c, actor_id)
        if c.execute("UPDATE users SET salt=?, pw_hash=? WHERE id=?", (salt, h, target_id)).rowcount == 0:
            raise ValueError("Akun tidak ditemukan")

def activate_package(actor_id, target_id, package_id, method):
    """Alur kasir sekali jalan: buat pesanan lalu langsung konfirmasi bayar. Return masa aktif baru."""
    with conn() as c:
        _require_admin(c, actor_id)
        t = c.execute("SELECT role FROM users WHERE id=?", (target_id,)).fetchone()
        if not t:
            raise ValueError("Akun tidak ditemukan")
        if t["role"] == "admin":
            raise ValueError("Admin sudah punya akses tanpa batas, tidak perlu paket")
    return confirm_payment(create_order(target_id, package_id, method))
