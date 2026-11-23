"""Fungsi bantu yang dipakai semua router: template, pesan, password, dan cek login."""
import csv
import io
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
from fastapi import Depends, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from database import ambil_satu, get_db

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

NAMA_APLIKASI = "W-allet"
WIB = timezone(timedelta(hours=7))

LABEL_JENIS = {
    "topup": "Isi Saldo",
    "kirim": "Kirim Saldo",
    "terima": "Terima Saldo",
    "bayar": "Bayar Layanan",
}

# SELECT dasar untuk menampilkan transaksi lengkap dengan nama-namanya.
# Kolom masuk dan keluar dihitung di sini supaya HTML tinggal menampilkan.
SQL_TRANSAKSI = """
    SELECT t.id, t.pengguna_id, t.waktu, t.jenis, t.nominal, t.biaya_admin, t.saldo_akhir,
           t.catatan, t.nomor_tujuan,
           p.nama AS nama_pengguna, p.no_hp AS hp_pengguna,
           m.nama_metode, l.nama_layanan, k.nama_kategori,
           w.nama AS nama_lawan, w.no_hp AS hp_lawan,
           CASE WHEN t.jenis IN ('topup', 'terima') THEN t.nominal ELSE 0 END AS masuk,
           CASE WHEN t.jenis IN ('kirim', 'bayar') THEN t.nominal + t.biaya_admin ELSE 0 END AS keluar
    FROM transaksi t
    JOIN pengguna p ON p.id = t.pengguna_id
    LEFT JOIN metode_topup m ON m.id = t.metode_id
    LEFT JOIN layanan l ON l.id = t.layanan_id
    LEFT JOIN kategori k ON k.id = l.kategori_id
    LEFT JOIN pengguna w ON w.id = t.lawan_id
"""


# ---------- Waktu dan tampilan ----------

def sekarang():
    """Waktu saat ini dalam WIB, sama dengan isi kolom waktu di database."""
    return datetime.now(WIB).replace(tzinfo=None)


def rupiah(nilai):
    """150000 -> Rp 150.000"""
    return "Rp " + f"{nilai or 0:,.0f}".replace(",", ".")


def keterangan(t):
    """Kalimat singkat yang menjelaskan satu baris transaksi."""
    if t["jenis"] == "topup":
        teks = f"Isi saldo via {t['nama_metode']}"
    elif t["jenis"] == "kirim":
        teks = f"Kirim ke {t['nama_lawan']}"
    elif t["jenis"] == "terima":
        teks = f"Terima dari {t['nama_lawan']}"
    else:
        teks = t["nama_layanan"]
        if t["nomor_tujuan"]:
            teks += f" ({t['nomor_tujuan']})"
    if t["catatan"]:
        teks += f", {t['catatan']}"
    return teks


def kode_transaksi(nomor):
    """15 -> TRX-000015"""
    return f"TRX-{nomor:06d}"


def tanggal(waktu):
    return waktu.strftime("%d-%m-%Y %H:%M")


templates.env.filters["rupiah"] = rupiah
templates.env.filters["keterangan"] = keterangan
templates.env.filters["tanggal"] = tanggal
templates.env.filters["kode"] = kode_transaksi
templates.env.globals.update(NAMA_APLIKASI=NAMA_APLIKASI, LABEL_JENIS=LABEL_JENIS)


def pesan(request, teks, tipe="sukses"):
    """Simpan pesan untuk ditampilkan satu kali di halaman berikutnya."""
    request.session["pesan"] = {"teks": teks, "tipe": tipe}


def render(request, nama_file, user=None, **data):
    """Tampilkan template. Data user dan pesan selalu ikut dikirim."""
    data["user"] = user
    data["pesan"] = request.session.pop("pesan", None)
    return templates.TemplateResponse(request=request, name=nama_file, context=data)


def alihkan(url):
    """Pindah halaman setelah form POST selesai diproses."""
    return RedirectResponse(url, status_code=303)


def unduh_csv(nama_file, judul_kolom, baris):
    """Kirim data sebagai file CSV yang bisa dibuka di Excel.

    Pemisah titik koma dan BOM UTF-8 dipakai supaya Excel berbahasa Indonesia
    langsung memisahkan kolom dengan benar.
    """
    buffer = io.StringIO()
    penulis = csv.writer(buffer, delimiter=";")
    penulis.writerow(judul_kolom)
    for isi in baris:
        # Teks yang diawali = + - @ bisa dianggap rumus oleh Excel, jadi diberi tanda kutip.
        penulis.writerow([
            "'" + nilai if isinstance(nilai, str) and nilai[:1] in ("=", "+", "-", "@") else nilai
            for nilai in isi
        ])
    return Response(
        "\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nama_file}"'},
    )


# ---------- Password ----------

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def cek_password(password, hash_tersimpan):
    if len(password.encode()) > 72:  # batas panjang bcrypt
        return False
    return bcrypt.checkpw(password.encode(), hash_tersimpan.encode())


def periksa_password(password, ulangi):
    """Kembalikan teks kesalahan, atau None kalau password boleh dipakai."""
    if not 6 <= len(password) <= 50:
        return "Password harus 6 sampai 50 karakter."
    if password != ulangi:
        return "Ulangi password tidak sama."
    return None


# ---------- Validasi isian form ----------

def periksa_data_diri(nama, no_hp):
    """Kembalikan teks kesalahan, atau None kalau nama dan nomor HP sudah benar."""
    if not 3 <= len(nama) <= 100:
        return "Nama harus 3 sampai 100 huruf."
    if not re.fullmatch(r"08\d{8,13}", no_hp):
        return "Nomor HP harus diawali 08 dan berisi 10 sampai 15 angka."
    return None


def periksa_email(email):
    if len(email) > 100 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return "Format email tidak benar (maksimal 100 karakter)."
    return None


def periksa_teks(nilai, label, maks, wajib=True):
    """Cek panjang teks supaya tidak melebihi ukuran kolom di database."""
    if wajib and not nilai:
        return f"{label} wajib diisi."
    if len(nilai) > maks:
        return f"{label} maksimal {maks} karakter."
    return None


# ---------- Cek login (dipasang di endpoint lewat Depends) ----------

class Alihkan(Exception):
    """Dilempar saat pengunjung harus dipindah ke halaman lain, misalnya belum login."""

    def __init__(self, url, teks=None):
        self.url = url
        self.teks = teks


def user_login(request: Request, db=Depends(get_db)):
    """Data pengguna yang sedang login. Kalau belum login, pindah ke halaman login."""
    user = None
    if request.session.get("user_id"):
        user = ambil_satu(
            db,
            "SELECT id, nama, email, no_hp, role, saldo FROM pengguna WHERE id = %s AND aktif",
            (request.session["user_id"],),
        )
    if not user:
        request.session.clear()
        raise Alihkan("/login")
    return user


def khusus_admin(user=Depends(user_login)):
    if user["role"] != "admin":
        raise Alihkan("/", "Halaman itu khusus admin.")
    return user


def khusus_pengguna(user=Depends(user_login)):
    if user["role"] != "pengguna":
        raise Alihkan("/", "Admin tidak punya saldo, jadi tidak bisa bertransaksi.")
    return user
