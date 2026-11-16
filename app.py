import pandas as pd, plotly.express as px, streamlit as st
from core import analytics as A, db, seed, service as S

db.init()
st.set_page_config("Malibu Gym V2", "🏋️", layout="wide")
rp = lambda x: f"Rp {int(x):,}".replace(",", ".")

def auth():
    st.title("🏋️ Malibu Gym V2")
    st.caption("Prototype akademik — gerbang & pembayaran adalah simulasi.")
    if not db.admin_exists():
        st.warning("Akun admin belum dibuat. Buat file `.env` (salin dari `.env.example`, isi ADMIN_EMAIL dan "
                   "ADMIN_PASSWORD), lalu restart aplikasi. Atau jalankan: `python -m scripts.create_admin`.")
    t1, t2 = st.tabs(["Masuk", "Daftar"])
    with t1:
        e, p = st.text_input("Email", key="le"), st.text_input("Password", type="password", key="lp")
        if st.button("Masuk"):
            u = S.login(e, p)
            if u: st.session_state.uid = u["id"]; st.rerun()
            else: st.error("Email atau password salah")
    with t2:
        n, e, p = st.text_input("Nama"), st.text_input("Email", key="re"), st.text_input("Password (min 8)", type="password", key="rp")
        if st.button("Daftar"):
            try: S.register(n, e, p); st.success("Registrasi berhasil, silakan masuk.")
            except ValueError as ex: st.error(str(ex))

def member_pages(u, page):
    if page == "Paket & Bayar":
        st.header("Pilih Paket")
        pk = {f"{p['name']} — {p['days']} hari — {rp(p['price'])}": p["id"] for p in S.packages()}
        choice, method = st.selectbox("Paket", list(pk)), st.radio("Metode bayar (dibayar di kasir)", S.METHODS, horizontal=True)
        if st.button("Buat pesanan"):
            S.create_order(u["id"], pk[choice], method); st.success("Pesanan dibuat. Selesaikan pembayaran di kasir.")
        st.subheader("Riwayat"); o = S.my_orders(u["id"])
        st.dataframe(pd.DataFrame(o), use_container_width=True) if o else st.info("Belum ada transaksi.")
    elif page == "QR Saya":
        st.header("QR Code Akses")
        if u["qr_token"] and u["active_until"] and S.parse(u["active_until"]) >= S.now():
            st.image(S.qr_png(u["qr_token"]), width=260); st.success(f"Aktif sampai {u['active_until']}")
        elif u["qr_token"]: st.warning(f"Masa aktif habis ({u['active_until']}). Silakan perpanjang.")
        else: st.info("QR terbit setelah pembayaran dikonfirmasi kasir.")
    else:
        st.header("Notifikasi")
        n = S.notifications(u["id"])
        for x in n: st.info(f"{x['created_at']} — {x['message']}")
        if not n: st.write("Belum ada notifikasi.")

def admin_pages(page, u):
    if page == "Dashboard":
        st.header("Dashboard Operasional & Analisis")
        k = A.kpis(); c = st.columns(4)
        c[0].metric("Omzet total", rp(k["revenue"])); c[1].metric("Omzet hari ini", rp(k["revenue_today"]))
        c[2].metric("Member aktif", int(k["active_members"])); c[3].metric("Kunjungan hari ini", int(k["visits_today"]))
        rd = A.revenue_daily()
        if rd.empty: st.info("Belum ada data. Konfirmasi transaksi atau buat data sintetis di menu 'Data & Notifikasi'."); return
        st.plotly_chart(px.bar(rd, x="date", y="revenue", title="Omzet harian"), use_container_width=True)
        h = A.busiest()
        if h is not None: st.plotly_chart(px.imshow(h, aspect="auto", color_continuous_scale="Reds",
                          labels=dict(x="Jam", y="Hari", color="Kunjungan"), title="Jam tersibuk"), use_container_width=True)
        df = A.features(); cl, sil = A.clusters(df)
        if cl is None: st.info("Data member belum cukup untuk clustering/churn."); return
        st.subheader(f"Clustering member (KMeans, silhouette={sil})")
        st.plotly_chart(px.scatter(cl, x="frequency", y="recency", color="cluster", hover_data=["name", "tenure"]), use_container_width=True)
        st.dataframe(cl.groupby("cluster")[A.FEATS].mean().round(1).assign(jumlah=cl.cluster.value_counts()))
        m, act = A.churn_model(df)
        if m is None: st.info("Data historis belum cukup untuk model churn."); return
        st.subheader("Prediksi churn"); st.dataframe(m, hide_index=True)
        st.caption("Jika data sintetis dipakai, metrik hanya untuk demo.")
        st.dataframe(act[act.at_risk][["id", "name", "frequency", "recency", "churn_prob"]], hide_index=True)
    elif page == "Kasir":
        st.header("Konfirmasi Pembayaran"); o = S.pending_orders()
        if not o: st.info("Tidak ada pesanan pending.")
        for x in o:
            a, b = st.columns([4, 1]); a.write(f"#{x['id']} · {x['name']} · {x['paket']} · {rp(x['amount'])} · {x['method']}")
            if b.button("Konfirmasi", key=f"c{x['id']}"):
                S.confirm_payment(x["id"]); st.rerun()
    elif page == "Kelola Member":
        st.header("Kelola Member & Akun")
        users = S.list_users(u["id"])
        st.dataframe(pd.DataFrame(users), use_container_width=True, hide_index=True)
        st.caption("Akun sintetis (demo) tidak ditampilkan.")
        opts = {f"#{x['id']} · {x['name']} · {x['email']} ({x['role']})": x["id"] for x in users}
        tid = opts[st.selectbox("Pilih akun", list(opts))]
        t1, t2, t3 = st.tabs(["Aktifkan paket", "Reset password", "Ubah peran"])
        with t1:
            pk = {f"{p['name']} — {p['days']} hari — {rp(p['price'])}": p["id"] for p in S.packages()}
            ch, mt = st.selectbox("Paket", list(pk), key="mp"), st.radio("Metode bayar", S.METHODS, horizontal=True, key="mm")
            if st.button("Aktifkan sekarang", key="mb"):
                try: st.success(f"Aktif sampai {S.activate_package(u['id'], tid, pk[ch], mt)}")
                except (ValueError, PermissionError) as ex: st.error(str(ex))
        with t2:
            npw = st.text_input("Password baru (min 8)", type="password", key="np")
            if st.button("Reset password", key="nb"):
                try: S.reset_password(u["id"], tid, npw); st.success("Password diperbarui.")
                except (ValueError, PermissionError) as ex: st.error(str(ex))
        with t3:
            role = st.radio("Peran", ["member", "admin"], horizontal=True, key="rr")
            if st.button("Simpan peran", key="rb"):
                try: S.set_role(u["id"], tid, role); st.success("Peran diperbarui."); st.rerun()
                except (ValueError, PermissionError) as ex: st.error(str(ex))
    elif page == "Gate (Simulasi)":
        st.header("Smart Access Gate")
        tok = st.text_input("Token QR (atau gunakan kamera)")
        img = st.camera_input("Scan QR")
        if st.button("Scan"):
            if img: tok = S.decode_qr(img.getvalue()) or tok
            ok, msg = S.scan(tok); (st.success if ok else st.error)(("🟢 " if ok else "🔴 ") + msg)
    elif page == "Alert":
        st.header("Alert Keamanan"); a = S.alerts()
        st.dataframe(pd.DataFrame(a), use_container_width=True) if a else st.info("Tidak ada alert.")
    else:
        st.header("Data & Notifikasi")
        if st.button("Buat 150 member SINTETIS (demo)"): st.success(f"{seed.seed(150)} member sintetis dibuat")
        if st.button("Kirim notifikasi ke member At-Risk"):
            _, act = A.churn_model(A.features())
            if act is None: st.warning("Data belum cukup.")
            else:
                ids = act[act.at_risk].id.tolist()
                S.notify(ids, "Masa aktifmu segera berakhir — perpanjang sekarang & dapatkan promo!"); st.success(f"{len(ids)} notifikasi terkirim (log aplikasi)")

uid = st.session_state.get("uid")
u = S.get_user(uid) if uid else None
if not u: auth(); st.stop()
ADMIN_PAGES = ["Dashboard", "Kasir", "Kelola Member", "Gate (Simulasi)", "Alert", "Data & Notifikasi"]
MEMBER_PAGES = ["Paket & Bayar", "QR Saya", "Notifikasi"]
is_admin = u["role"] == "admin"
pages = ADMIN_PAGES + MEMBER_PAGES if is_admin else MEMBER_PAGES  # admin: akses ke semua fitur
st.sidebar.write(f"👤 {u['name']} ({u['role']})")
page = st.sidebar.radio("Menu", pages)
if st.sidebar.button("Keluar"): st.session_state.pop("uid"); st.rerun()
if page in ADMIN_PAGES and is_admin: admin_pages(page, u)
else: member_pages(u, page)
