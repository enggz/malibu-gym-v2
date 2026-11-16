# Malibu Gym V2 (prototype)

Prototype transformasi digital Gym Malibu: registrasi member, paket & kasir, QR Code akses, gate simulasi,
alert keamanan, dashboard operasional, jam tersibuk, clustering KMeans, prediksi churn
(Logistic Regression vs Random Forest), dan notifikasi member At-Risk.

**Stack:** Python, Streamlit, SQLite, pandas, scikit-learn, Plotly, qrcode, OpenCV.

---

## Cara pakai

### 1. Persiapan (sekali saja)

Butuh Python 3.10 atau lebih baru.

```bash
cd malibu-gym-v2
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
```

Buka file `.env` lalu **ganti `ADMIN_PASSWORD`** (minimal 8 karakter). Isi file `.env`:

| Variabel         | Fungsi                                                          | Contoh                  |
|------------------|-----------------------------------------------------------------|-------------------------|
| `DB_PATH`        | Lokasi file database SQLite (relatif ke folder proyek)          | `malibu.db`             |
| `ADMIN_EMAIL`    | Email untuk login admin                                         | `admin@malibu.local`    |
| `ADMIN_PASSWORD` | Password admin                                                  | `adminmalibu123`        |
>>>>>>> 8a7318da1f2769857e677cf2e6095d8dbfd51ba4

> Tidak perlu membuat database secara manual. File `malibu.db`, semua tabel, dan 4 paket default
> (Harian, Bulanan, Triwulan, Tahunan) dibuat **otomatis** saat aplikasi dijalankan.

### 2. Menjalankan

```bash
streamlit run app.py
```

Buka alamat yang tampil di terminal (biasanya http://localhost:8501).

### 3. Login admin

Masuk di tab **Masuk** dengan `ADMIN_EMAIL` dan `ADMIN_PASSWORD` dari `.env`.
Jika admin belum ada, halaman login menampilkan peringatan kuning berisi langkah perbaikannya.

### 4. Alur demo yang disarankan

1. **Member** mendaftar di tab *Daftar*, lalu masuk, pilih paket di *Paket & Bayar*, dan klik *Buat pesanan*.
2. **Admin** membuka *Kasir*, lalu klik *Konfirmasi*. Masa aktif dan QR member terbit.
3. Member membuka *QR Saya* untuk melihat QR Code.
4. **Admin** membuka *Gate (Simulasi)*, lalu menempel token QR atau memakai kamera. Hasilnya diizinkan,
   atau ditolak (QR tidak dikenal, masa aktif habis, atau scan ganda dalam 10 menit) disertai *Alert*.
5. Untuk mencoba analisis, buka *Data & Notifikasi*, klik **Buat 150 member SINTETIS**, lalu buka *Dashboard*.
6. Klik **Kirim notifikasi ke member At-Risk**. Notifikasi tercatat di log aplikasi (bukan dikirim sungguhan).

### 5. Menjalankan tes

```bash
python -m pytest -q
```

Tes memakai database sementara dan akun admin sendiri, jadi tidak menyentuh `malibu.db` maupun `.env` Anda.

---

## Hak akses

| Fitur                                              | Member | Admin |
|----------------------------------------------------|:------:|:-----:|
| Paket & Bayar, QR Saya, Notifikasi                 |   ✅   |  ✅   |
| Dashboard, Kasir, Gate, Alert, Data & Notifikasi   |   ❌   |  ✅   |
| Kelola Member (aktifkan paket, reset password, ubah peran) | ❌ | ✅ |

Admin memiliki **akses penuh ke semua fitur**, ditambah:

- **Masa aktif tanpa batas** (sampai 2099-12-31) dan QR akses sendiri.
- **Gate selalu terbuka** untuk QR admin: tanpa cek kedaluwarsa dan tanpa deteksi scan ganda.
- Kunjungan admin **tidak dihitung** di statistik (kunjungan hari ini, jam tersibuk, clustering, churn),
  supaya data analisis tetap murni data member.
- Halaman **Kelola Member**: lihat semua akun, aktifkan paket langsung (kasir sekali jalan),
  reset password, dan promosikan member menjadi admin (atau sebaliknya).
  Admin tidak bisa mengubah peran akunnya sendiri, supaya tidak terkunci dari sistem.

Fungsi manajemen akun memeriksa peran **di lapisan service** (`PermissionError` bila bukan admin),
bukan hanya menyembunyikan menu di UI.

---

## Struktur folder

```
malibu-gym-v2/
├── app.py               # Antarmuka Streamlit: login/daftar, halaman member, halaman admin, navigasi per peran
├── core/
│   ├── db.py            # Skema SQLite, koneksi, pembuatan admin otomatis dari .env, paket default
│   ├── service.py       # Logika bisnis: registrasi, login, pesanan, pembayaran, QR, gate, alert,
│   │                    #   notifikasi, manajemen akun admin
│   ├── analytics.py     # KPI, omzet harian, jam tersibuk, fitur member, KMeans, model churn
│   └── seed.py          # Generator data SINTETIS untuk demo analisis
├── scripts/
│   └── create_admin.py  # Perintah untuk membuat / mereset akun admin tanpa membuka database
├── tests/
│   ├── conftest.py      # Mengarahkan tes ke DB sementara + akun admin tes
│   └── test_core.py     # Tes registrasi, pembayaran, gate, analitik, dan fitur admin
├── .env.example         # Contoh konfigurasi (salin menjadi .env)
├── requirements.txt     # Daftar dependensi
└── .gitignore           # .env, *.db, cache tidak ikut ke Git
```

File yang muncul setelah aplikasi dijalankan (tidak masuk Git): `.env` (konfigurasi Anda) dan `malibu.db` (database).

**Mengapa dipisah begini?** `app.py` hanya urusan tampilan. Aturan bisnis ada di `core/service.py` dan analisis di
`core/analytics.py`, sehingga keduanya bisa dites tanpa membuka UI (itulah isi `tests/`).
Ganti database nantinya cukup menyentuh `core/db.py`.

---

## Masalah umum: admin tidak bisa login

Database **bukan** penyebabnya, karena dibuat otomatis. Akun admin hanya dibuat jika `ADMIN_EMAIL` dan
`ADMIN_PASSWORD` terbaca saat aplikasi mulai. Cek berurutan:

1. **File `.env` belum dibuat.** Hanya ada `.env.example`? Jalankan `cp .env.example .env`, isi password, lalu restart Streamlit.
2. **`.env` salah tempat.** Harus berada di folder yang sama dengan `app.py` (bukan di dalam `core/`).
3. **Lupa password / mengganti password di `.env`.** Password di `.env` hanya dipakai **saat akun admin pertama dibuat**.
   Mengubahnya kemudian tidak mengubah akun yang sudah ada. Reset dengan:
   ```bash
   python -m scripts.create_admin email@contoh.com PasswordBaru123
   ```
   (tanpa argumen, skrip akan menanyakan email dan password.) Skrip ini juga memperbaiki akun yang terlanjur
   berstatus member karena email tersebut sempat didaftarkan lewat form *Daftar*.
4. **Email salah ketik.** Login tidak peka huruf besar/kecil, tetapi tidak boleh ada typo.
5. **Di Streamlit Cloud**, isi `ADMIN_EMAIL`, `ADMIN_PASSWORD`, dan `DB_PATH` di *Secrets*, lalu reboot app.

Ingin memulai dari nol? Hentikan aplikasi, hapus `malibu.db`, jalankan lagi. Semua data hilang, admin dibuat ulang dari `.env`.

---

## Deploy

Push ke GitHub, lalu deploy di Streamlit Community Cloud (isi `ADMIN_*` di *Secrets*). SQLite bersifat sementara
di cloud (data hilang saat app di-reboot); untuk produksi ganti ke Supabase/PostgreSQL.

## Keterbatasan

- Gerbang, pembayaran, dan notifikasi adalah **simulasi**.
- Label churn = masa aktif lewat tanpa perpanjangan; skor member aktif bersifat *in-sample*.
- Metrik pada data sintetis hanya untuk demo, bukan hasil data Gym Malibu sungguhan.
- Pengecekan peran penuh hanya pada fungsi manajemen akun; fungsi kasir dan lainnya masih dibatasi lewat menu UI.
- Mode internet mati belum ada.
