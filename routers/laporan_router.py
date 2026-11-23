"""File report: mutasi, rekap harian, rekap per kategori, per layanan, per metode, dan pengguna.

Pengguna biasa hanya melihat datanya sendiri. Admin melihat data semua pengguna.
Semua laporan bisa dicetak / disimpan sebagai PDF lewat tombol Cetak, dan
diunduh sebagai file CSV (bisa dibuka di Excel) lewat tombol Unduh CSV.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request

from database import ambil_semua, get_db
from helper import (
    LABEL_JENIS,
    SQL_TRANSAKSI,
    kode_transaksi,
    keterangan,
    khusus_admin,
    render,
    sekarang,
    tanggal,
    unduh_csv,
    user_login,
)

router = APIRouter(prefix="/laporan")

TANGGAL_TERAKHIR = date(9999, 12, 30)  # supaya "sampai + 1 hari" tidak melewati batas tahun


def baca_periode(dari, sampai):
    """Ubah teks tanggal dari form menjadi date. Kalau kosong: awal bulan ini s.d. hari ini.

    Kalau tanggal "dari" lebih besar dari "sampai", keduanya ditukar.
    """
    hari_ini = sekarang().date()
    try:
        tgl_dari = date.fromisoformat(dari)
    except ValueError:
        tgl_dari = hari_ini.replace(day=1)
    try:
        tgl_sampai = date.fromisoformat(sampai)
    except ValueError:
        tgl_sampai = hari_ini
    if tgl_dari > tgl_sampai:
        tgl_dari, tgl_sampai = tgl_sampai, tgl_dari
    return min(tgl_dari, TANGGAL_TERAKHIR), min(tgl_sampai, TANGGAL_TERAKHIR)


def syarat_periode(user, tgl_dari, tgl_sampai):
    """Syarat WHERE dasar: rentang tanggal, dan khusus pengguna biasa hanya datanya sendiri."""
    syarat = ["t.waktu >= %s", "t.waktu < %s"]
    params = [tgl_dari, tgl_sampai + timedelta(days=1)]
    if user["role"] == "pengguna":
        syarat.append("t.pengguna_id = %s")
        params.append(user["id"])
    return syarat, params


def nama_file(awalan, tgl_dari, tgl_sampai):
    return f"{awalan}_{tgl_dari:%Y%m%d}-{tgl_sampai:%Y%m%d}.csv"


@router.get("")
def menu_laporan(request: Request, user=Depends(user_login)):
    return render(request, "laporan/menu.html", user)


# ---------- Mutasi / laporan transaksi ----------

@router.get("/mutasi")
def laporan_mutasi(
    request: Request,
    dari: str = "",
    sampai: str = "",
    jenis: str = "",
    format: str = "",
    user=Depends(user_login),
    db=Depends(get_db),
):
    tgl_dari, tgl_sampai = baca_periode(dari, sampai)

    # Syarat WHERE disusun bertahap sesuai filter yang dipilih.
    syarat, params = syarat_periode(user, tgl_dari, tgl_sampai)
    if jenis in LABEL_JENIS:
        syarat.append("t.jenis = %s")
        params.append(jenis)
    else:
        jenis = ""

    data = ambil_semua(
        db,
        SQL_TRANSAKSI + " WHERE " + " AND ".join(syarat) + " ORDER BY t.waktu DESC, t.id DESC",
        params,
    )

    if format == "csv":
        return unduh_csv(
            nama_file("mutasi", tgl_dari, tgl_sampai),
            ["Kode", "Waktu", "Pengguna", "Jenis", "Keterangan",
             "Masuk", "Keluar", "Biaya Admin", "Saldo Akhir"],
            [
                [kode_transaksi(t["id"]), tanggal(t["waktu"]), t["nama_pengguna"],
                 LABEL_JENIS[t["jenis"]], keterangan(t),
                 int(t["masuk"]), int(t["keluar"]), int(t["biaya_admin"]), int(t["saldo_akhir"])]
                for t in data
            ],
        )

    return render(
        request, "laporan/mutasi.html", user,
        data=data, dari=tgl_dari, sampai=tgl_sampai, jenis=jenis,
        total_masuk=sum(t["masuk"] for t in data),
        total_keluar=sum(t["keluar"] for t in data),
    )


# ---------- Rekap harian ----------

@router.get("/harian")
def rekap_harian(
    request: Request,
    dari: str = "",
    sampai: str = "",
    format: str = "",
    user=Depends(user_login),
    db=Depends(get_db),
):
    tgl_dari, tgl_sampai = baca_periode(dari, sampai)
    syarat, params = syarat_periode(user, tgl_dari, tgl_sampai)
    admin = user["role"] == "admin"
    if admin:
        # Satu transfer tercatat dua baris (kirim + terima). Admin cukup menghitung sekali.
        syarat.append("t.jenis <> 'terima'")

    data = ambil_semua(
        db,
        """
        SELECT t.waktu::date AS tanggal,
               COUNT(*) AS jumlah,
               COALESCE(SUM(t.nominal) FILTER (WHERE t.jenis = 'topup'), 0) AS topup,
               COALESCE(SUM(t.nominal) FILTER (WHERE t.jenis = 'terima'), 0) AS terima,
               COALESCE(SUM(t.nominal) FILTER (WHERE t.jenis = 'kirim'), 0) AS kirim,
               COALESCE(SUM(t.nominal) FILTER (WHERE t.jenis = 'bayar'), 0) AS bayar,
               COALESCE(SUM(t.biaya_admin), 0) AS biaya_admin
        FROM transaksi t
        WHERE """ + " AND ".join(syarat) + """
        GROUP BY t.waktu::date
        ORDER BY t.waktu::date
        """,
        params,
    )

    if format == "csv":
        kolom = ["Tanggal", "Jumlah Transaksi", "Isi Saldo"]
        kolom += [] if admin else ["Terima"]
        kolom += ["Kirim", "Bayar Layanan", "Biaya Admin"]
        return unduh_csv(
            nama_file("rekap_harian", tgl_dari, tgl_sampai),
            kolom,
            [
                [f"{b['tanggal']:%d-%m-%Y}", b["jumlah"], int(b["topup"])]
                + ([] if admin else [int(b["terima"])])
                + [int(b["kirim"]), int(b["bayar"]), int(b["biaya_admin"])]
                for b in data
            ],
        )

    return render(
        request, "laporan/harian.html", user,
        data=data, dari=tgl_dari, sampai=tgl_sampai, admin=admin, alamat="/laporan/harian",
    )


# ---------- Rekap per kategori / layanan / metode ----------

def tampil_rekap(request, user, data, tgl_dari, tgl_sampai, format, judul, kolom, alamat,
                 awalan_file, ada_biaya=True):
    """Satu fungsi untuk menampilkan atau mengunduh semua laporan rekap."""
    if format == "csv":
        judul_kolom = [kolom, "Jumlah Transaksi", "Nominal"]
        judul_kolom += ["Biaya Admin", "Total"] if ada_biaya else []
        return unduh_csv(
            nama_file(awalan_file, tgl_dari, tgl_sampai),
            judul_kolom,
            [
                [b["nama"], b["jumlah"], int(b["nominal"])]
                + ([int(b["biaya_admin"]), int(b["total"])] if ada_biaya else [])
                for b in data
            ],
        )
    return render(
        request, "laporan/rekap.html", user,
        judul=judul, kolom=kolom, alamat=alamat, ada_biaya=ada_biaya,
        data=data, dari=tgl_dari, sampai=tgl_sampai,
    )


@router.get("/kategori")
def rekap_kategori(
    request: Request,
    dari: str = "",
    sampai: str = "",
    format: str = "",
    user=Depends(user_login),
    db=Depends(get_db),
):
    tgl_dari, tgl_sampai = baca_periode(dari, sampai)
    syarat, params = syarat_periode(user, tgl_dari, tgl_sampai)
    data = ambil_semua(
        db,
        """
        SELECT k.nama_kategori AS nama,
               COUNT(*) AS jumlah,
               SUM(t.nominal) AS nominal,
               SUM(t.biaya_admin) AS biaya_admin,
               SUM(t.nominal + t.biaya_admin) AS total
        FROM transaksi t
        JOIN layanan l ON l.id = t.layanan_id
        JOIN kategori k ON k.id = l.kategori_id
        WHERE """ + " AND ".join(syarat) + """
        GROUP BY k.nama_kategori
        ORDER BY total DESC
        """,
        params,
    )
    return tampil_rekap(
        request, user, data, tgl_dari, tgl_sampai, format,
        "Rekap Pengeluaran per Kategori", "Kategori", "/laporan/kategori", "rekap_kategori",
    )


@router.get("/layanan")
def rekap_layanan(
    request: Request,
    dari: str = "",
    sampai: str = "",
    format: str = "",
    admin=Depends(khusus_admin),
    db=Depends(get_db),
):
    tgl_dari, tgl_sampai = baca_periode(dari, sampai)
    data = ambil_semua(
        db,
        """
        SELECT l.nama_layanan AS nama,
               COUNT(*) AS jumlah,
               SUM(t.nominal) AS nominal,
               SUM(t.biaya_admin) AS biaya_admin,
               SUM(t.nominal + t.biaya_admin) AS total
        FROM transaksi t
        JOIN layanan l ON l.id = t.layanan_id
        WHERE t.waktu >= %s AND t.waktu < %s
        GROUP BY l.nama_layanan
        ORDER BY total DESC
        """,
        (tgl_dari, tgl_sampai + timedelta(days=1)),
    )
    return tampil_rekap(
        request, admin, data, tgl_dari, tgl_sampai, format,
        "Rekap Transaksi per Layanan", "Layanan", "/laporan/layanan", "rekap_layanan",
    )


@router.get("/metode")
def rekap_metode(
    request: Request,
    dari: str = "",
    sampai: str = "",
    format: str = "",
    admin=Depends(khusus_admin),
    db=Depends(get_db),
):
    tgl_dari, tgl_sampai = baca_periode(dari, sampai)
    data = ambil_semua(
        db,
        """
        SELECT m.nama_metode AS nama,
               COUNT(*) AS jumlah,
               SUM(t.nominal) AS nominal
        FROM transaksi t
        JOIN metode_topup m ON m.id = t.metode_id
        WHERE t.jenis = 'topup' AND t.waktu >= %s AND t.waktu < %s
        GROUP BY m.nama_metode
        ORDER BY nominal DESC
        """,
        (tgl_dari, tgl_sampai + timedelta(days=1)),
    )
    return tampil_rekap(
        request, admin, data, tgl_dari, tgl_sampai, format,
        "Rekap Isi Saldo per Metode", "Metode", "/laporan/metode", "rekap_metode",
        ada_biaya=False,
    )


# ---------- Laporan pengguna ----------

@router.get("/pengguna")
def laporan_pengguna(
    request: Request, format: str = "", admin=Depends(khusus_admin), db=Depends(get_db)
):
    data = ambil_semua(
        db,
        """
        SELECT p.nama, p.email, p.no_hp, p.saldo, p.aktif, p.dibuat_pada,
               COUNT(t.id) AS jumlah_transaksi
        FROM pengguna p
        LEFT JOIN transaksi t ON t.pengguna_id = p.id
        WHERE p.role = 'pengguna'
        GROUP BY p.id
        ORDER BY p.nama
        """,
    )
    if format == "csv":
        return unduh_csv(
            f"laporan_pengguna_{sekarang():%Y%m%d}.csv",
            ["Nama", "Email", "Nomor HP", "Terdaftar", "Status", "Jumlah Transaksi", "Saldo"],
            [
                [p["nama"], p["email"], p["no_hp"], tanggal(p["dibuat_pada"]),
                 "Aktif" if p["aktif"] else "Nonaktif", p["jumlah_transaksi"], int(p["saldo"])]
                for p in data
            ],
        )
    return render(
        request, "laporan/pengguna.html", admin,
        data=data, total_saldo=sum(p["saldo"] for p in data), dicetak=sekarang(),
    )
