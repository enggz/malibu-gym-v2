from datetime import timedelta
import pytest
from core import analytics as A, db, seed, service as S
db.init()

def _member(email="a@x.com"):
    uid = S.register("Ani", email, "password123")
    tx = S.create_order(uid, 2, "QRIS"); S.confirm_payment(tx)
    return S.get_user(uid)

def test_register_validation():
    with pytest.raises(ValueError): S.register("A", "bad", "password123")
    with pytest.raises(ValueError): S.register("A", "ok@x.com", "short")
    _member("dup@x.com")
    with pytest.raises(ValueError): S.register("A", "dup@x.com", "password123")

def test_login():
    _member("l@x.com")
    assert S.login("l@x.com", "password123") and not S.login("l@x.com", "salah")

def test_payment_activates_and_extends():
    u = _member("p@x.com"); assert u["qr_token"] and u["active_until"]
    tx = S.create_order(u["id"], 2, "Tunai"); end2 = S.confirm_payment(tx)
    assert S.parse(end2) - S.parse(u["active_until"]) == timedelta(days=30)
    with pytest.raises(ValueError): S.confirm_payment(tx)

def test_gate_scenarios():
    u = _member("g@x.com")
    assert S.scan(u["qr_token"])[0]
    ok, msg = S.scan(u["qr_token"]); assert not ok and "ganda" in msg
    assert not S.scan("palsu")[0]
    assert not S.scan(u["qr_token"], at=S.now() + timedelta(days=60))[0]
    assert len(S.alerts()) >= 3

def test_analytics_on_seed():
    seed.seed(120)
    assert A.busiest() is not None
    df = A.features(); cl, sil = A.clusters(df); assert cl is not None
    m, act = A.churn_model(df); assert m is not None and len(act) > 0


# ---------------- Admin ----------------
def _admin():
    return S.login("admin@test.local", "adminpass123")

def test_admin_bootstrap_from_env():
    a = _admin()
    assert a and a["role"] == "admin"
    assert a["active_until"] == db.FOREVER and a["qr_token"]
    assert db.admin_exists()

def test_admin_gate_always_granted():
    a = _admin()
    assert S.scan(a["qr_token"])[0] and S.scan(a["qr_token"])[0]  # tanpa "scan ganda"
    assert S.scan(a["qr_token"], at=S.now() + timedelta(days=9999))[0]  # tanpa kedaluwarsa

def test_admin_excluded_from_member_analytics():
    a = _admin(); before = A.kpis()["visits_today"]
    S.scan(a["qr_token"])
    assert A.kpis()["visits_today"] == before

def test_member_email_hijack_is_overwritten():
    S.register("Penyusup", "claim@x.com", "passwordlama1")
    with db.conn() as c:
        db.upsert_admin(c, "claim@x.com", "passwordbaru1")
    assert not S.login("claim@x.com", "passwordlama1")
    assert S.login("claim@x.com", "passwordbaru1")["role"] == "admin"

def test_admin_management_and_permissions():
    a = _admin(); m = _member("mgr@x.com")
    assert any(u["id"] == m["id"] for u in S.list_users(a["id"]))
    end = S.activate_package(a["id"], m["id"], 1, "Tunai"); assert end
    S.reset_password(a["id"], m["id"], "passwordbaru1"); assert S.login("mgr@x.com", "passwordbaru1")
    S.set_role(a["id"], m["id"], "admin")
    assert S.get_user(m["id"])["role"] == "admin" and S.get_user(m["id"])["active_until"] == db.FOREVER
    S.set_role(a["id"], m["id"], "member")
    assert S.get_user(m["id"])["role"] == "member" and S.get_user(m["id"])["active_until"] != db.FOREVER
    with pytest.raises(ValueError): S.set_role(a["id"], a["id"], "member")  # tidak boleh menurunkan diri sendiri

def test_non_admin_cannot_manage():
    m = _member("nope@x.com"); t = _member("target@x.com")
    for call in (lambda: S.list_users(m["id"]), lambda: S.set_role(m["id"], t["id"], "admin"),
                 lambda: S.reset_password(m["id"], t["id"], "passwordbaru1"),
                 lambda: S.activate_package(m["id"], t["id"], 1, "Tunai")):
        with pytest.raises(PermissionError): call()

def test_cannot_activate_package_for_admin():
    a = _admin()
    with pytest.raises(ValueError): S.activate_package(a["id"], a["id"], 1, "Tunai")
