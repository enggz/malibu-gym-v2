"""Buat admin baru, atau reset password admin yang ada (juga memperbaiki akun yang terlanjur jadi member).

    python -m scripts.create_admin                      # akan menanyakan email & password
    python -m scripts.create_admin email@x.com password # langsung
"""
import sys
from getpass import getpass
from core import db

def main(argv):
    email = argv[0] if argv else input("Email admin: ").strip()
    pw = argv[1] if len(argv) > 1 else getpass("Password admin (min 8): ")
    if "@" not in email or len(pw) < 8:
        sys.exit("Email tidak valid atau password kurang dari 8 karakter.")
    db.init()
    with db.conn() as c:
        db.upsert_admin(c, email, pw)
        db.grant_admin_access(c)
    print(f"Admin siap: {email.strip().lower()}  (DB: {db.DB_PATH})")

if __name__ == "__main__":
    main(sys.argv[1:])
