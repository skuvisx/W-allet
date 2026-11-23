# W-allet

Dompet digital sederhana untuk Proyek Tugas Pemrograman Web Framework (Python).
Dibuat dengan FastAPI, Jinja2, dan PostgreSQL. Saldo di aplikasi ini hanya simulasi,
tidak terhubung ke bank atau uang sungguhan.

## Kesesuaian dengan ketentuan tugas

| No | Ketentuan | Implementasi di Aplikasi | File Kode |
|---|---|---|---|
| 1 | Basis data | PostgreSQL (5 tabel berelasi dengan `FOREIGN KEY`, `UNIQUE`, `CHECK (saldo >= 0)`, dan `INDEX`) | `schema.sql`, `database.py` |
| 2 | Login, register, dashboard | Login email + bcrypt, register pengguna baru, profil & ganti password, dashboard pengguna (grafik pengeluaran) dan dashboard admin (statistik ringkasan) | `routers/auth_router.py`, `routers/dashboard_router.py` |
| 3 | File master | CRUD lengkap untuk **Pengguna** (tambah, cari, edit, reset password, aktif/nonaktif, hapus), **Kategori**, **Layanan** (tambah, cari, edit, hapus), dan **Metode Isi Saldo** | `routers/master_router.py`, `templates/admin/` |
| 4 | File transaksi | **Isi Saldo (Top Up)**, **Kirim Saldo** (cek nama penerima otomatis & kunci transaksi anti-deadlock), **Bayar Layanan** (hitung total + biaya admin otomatis), serta **Bukti Transaksi / Struk** (`/transaksi/{id}`) yang bisa dicetak/PDF | `routers/transaksi_router.py`, `templates/struk.html` |
| 5 | File report | 6 laporan lengkap dengan filter periode, **Cetak / Simpan PDF**, dan **Unduh CSV (Excel)**: Mutasi Saldo / Laporan Transaksi, Rekap Harian, Rekap per Kategori (dengan persentase porsi), Rekap per Layanan, Rekap Isi Saldo per Metode, dan Laporan Pengguna | `routers/laporan_router.py`, `templates/laporan/` |
| 6 | Hosting gratis | Siap di-deploy gratis ke **Vercel** atau **Render** (aplikasi web) + **Neon** (PostgreSQL serverless gratis) | `main.py`, `render.yaml` |

## Menjalankan di laptop

### 1. Siapkan database

1. Buka pgAdmin, klik database `postgres`, buka Query Tool, lalu jalankan:

   ```sql
   CREATE DATABASE "db_w-allet";
   ```

   Tanda kutip dua wajib ditulis karena nama database memakai tanda hubung.

2. Klik database `db_w-allet`, buka Query Tool, buka file `schema.sql`, lalu jalankan semuanya (F5).

### 2. Siapkan project

Buka PowerShell di folder project ini, lalu:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Buka file `.env`, lalu ganti `admin` pada `DATABASE_URL` dengan password PostgreSQL di laptop.

### 3. Jalankan

```powershell
python -m uvicorn main:app --reload
```

Buka http://127.0.0.1:8000

## Akun bawaan

| Email | Password | Peran | Nomor HP |
|---|---|---|---|
| `admin@w-allet.test` | `admin123` | Admin | `080000000000` |
| `budi@w-allet.test` | `pengguna123` | Pengguna | `081200000001` |
| `siti@w-allet.test` | `pengguna123` | Pengguna | `081200000002` |

Akun baru dari halaman Daftar selalu berperan sebagai pengguna. Admin juga dapat menambahkan akun pengguna atau admin baru lewat menu **Pengguna > Tambah Pengguna**.

## Siapa bisa apa

| Peran | Menu & Fitur |
|---|---|
| Pengguna | Dashboard saldo & grafik kategori, Isi Saldo, Kirim Saldo (cek nama penerima otomatis), Bayar Layanan (kalkulasi biaya admin otomatis), Bukti Transaksi (Struk), Laporan (Mutasi, Rekap Harian, Rekap Kategori — cetak PDF & unduh CSV), Profil |
| Admin | Dashboard ringkasan, Master Pengguna (tambah, cari, edit, reset password, hapus), Master Kategori, Master Layanan (cari, tambah, edit, hapus), Master Metode Isi Saldo, Bukti Transaksi semua pengguna, 6 Laporan lengkap (cetak PDF & unduh CSV), Profil |

Admin tidak punya saldo, jadi tidak bisa melakukan transaksi saldo.

## Aturan transaksi & keamanan data

- **Isi saldo**: Rp 10.000 sampai Rp 2.000.000 per transaksi.
- **Kirim saldo**: Rp 1.000 sampai Rp 2.000.000, penerima dicari dari nomor HP, tanpa biaya admin. Menggunakan row-level locking (`SELECT ... FOR UPDATE` berurutan) supaya bebas *race condition* dan *deadlock*.
- **Bayar layanan**: Rp 1.000 sampai Rp 2.000.000, saldo dipotong nominal ditambah biaya admin layanan.
- **Saldo tidak bisa minus**: dijaga di kode (`WHERE saldo >= %s`) dan di database (`CHECK (saldo >= 0)`).
- **Transaksi bersifat permanen**: tidak bisa diubah atau dihapus supaya riwayat mutasi dan saldo akhir selalu konsisten.
- **Proteksi data master**: data master yang sudah dipakai transaksi (atau pengguna yang masih memiliki saldo) tidak bisa dihapus, melainkan dinonaktifkan.
- **Penanganan error ramah pengguna**: halaman 404, 405, 422 (validasi form), dan 500 ditampilkan dengan desain aplikasi yang rapi tanpa membocorkan detail teknis server.

## Struktur folder

```
W-allet/
├── main.py                  aplikasi FastAPI, session login, error handler, /health
├── database.py              koneksi PostgreSQL dan fungsi query
├── helper.py                template, filter Jinja2, validasi, ekspor CSV, cek login
├── schema.sql               tabel, constraint, indeks, dan data awal
├── requirements.txt         daftar paket Python
├── render.yaml              konfigurasi deploy otomatis di Render
├── .env.example             contoh isi file .env
├── routers/
│   ├── auth_router.py       login, register, logout, profil
│   ├── dashboard_router.py  dashboard pengguna dan admin
│   ├── transaksi_router.py  isi saldo, kirim, bayar, cek penerima, struk transaksi
│   ├── master_router.py     CRUD data master (admin)
│   └── laporan_router.py    6 laporan + ekspor CSV (Excel)
├── templates/               halaman HTML (Jinja2)
│   ├── admin/               halaman data master
│   └── laporan/             halaman laporan
└── static/
    ├── style.css            tampilan responsif dan mode cetak (print/PDF)
    └── fonts/               font Plus Jakarta Sans dan lisensinya
```

## Panduan Hosting Gratis (Neon + GitHub + Vercel / Render)

Aplikasi ini menggunakan **Neon** (database PostgreSQL gratis) dan bisa di-deploy gratis di **Vercel** (seperti `w-alletbytxc.vercel.app`, lebih cepat karena tidak tidur setelah 15 menit) maupun di **Render**.

### Langkah 1: Buat Database PostgreSQL Gratis di Neon

1. Buka https://neon.tech dan daftar/masuk (bisa langsung memakai akun GitHub atau Google).
2. Klik **New Project**, beri nama `w-allet`, pilih region terdekat (misalnya **Singapore**), lalu klik **Create Project**.
3. Di menu kiri Neon, buka **SQL Editor**.
4. Salin seluruh isi file `schema.sql` dari project ini, tempelkan ke SQL Editor Neon, lalu klik **Run** untuk membuat semua tabel beserta akun dan data awal.
5. Klik tombol **Connect** (atau buka **Dashboard > Connection Details**), lalu salin **Connection string** (formatnya `postgresql://neondb_owner:...@ep-...neon.tech/neondb?sslmode=require`).

### Langkah 2: Unggah Project ke GitHub

1. Buka https://github.com/new dan buat repository baru bernama `w-allet` (boleh Public atau Private, jangan centang *Add a README*).
2. Jalankan perintah berikut di PowerShell pada folder project ini (ganti `USERNAME` dengan username GitHub Anda):

   ```powershell
   git branch -M main
   git remote add origin https://github.com/USERNAME/w-allet.git
   git push -u origin main
   ```

### Langkah 3A: Deploy Gratis di Vercel (Direkomendasikan — Cepat & Tanpa Delay)

1. Buka https://vercel.com dan masuk menggunakan akun **GitHub**.
2. Klik **Add New...** > **Project**, lalu klik **Import** pada repository `w-allet`.
3. Vercel otomatis mendeteksi **FastAPI** dari `main.py`. Buka bagian **Environment Variables**, lalu tambahkan:
   - `DATABASE_URL` = *Connection string dari Neon*
   - `SECRET_KEY` = *teks acak panjang (misalnya 32 karakter acak)*
4. Klik **Deploy**. Dalam 1 menit aplikasi langsung aktif di `https://nama-project.vercel.app`.

### Langkah 3B: Alternatif Deploy Gratis di Render

#### Cara Otomatis dengan Blueprint (`render.yaml`)
1. Buka https://dashboard.render.com dan daftar/masuk dengan akun **GitHub**.
2. Klik **New +** > **Blueprint**, lalu pilih repository `w-allet`.
3. Render akan otomatis membaca file `render.yaml`. Pada kolom `DATABASE_URL`, tempelkan *Connection string* dari Neon.
4. Klik **Apply** / **Deploy** dan tunggu sekitar 2 menit sampai statusnya **Live**.

#### Cara Manual lewat Web Service
1. Di https://dashboard.render.com, klik **New +** > **Web Service**, lalu pilih repository `w-allet`.
2. Isi pengaturan berikut:
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: `Free`
3. Pada bagian **Environment Variables**, tambahkan:
   - `DATABASE_URL` = *Connection string dari Neon*
   - `SECRET_KEY` = *teks acak panjang (misalnya 32 karakter acak)*
   - `PYTHON_VERSION` = `3.12.8`
4. Klik **Create Web Service**. Setelah proses build selesai, klik alamat `https://w-allet-xxxx.onrender.com` di bagian atas untuk membuka aplikasi.
