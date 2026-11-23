"""File transaksi: isi saldo, kirim saldo, bayar layanan, dan bukti transaksi.

Setiap transaksi mengubah saldo di tabel pengguna DAN menambah baris di tabel
transaksi. Keduanya baru tersimpan saat db.commit(), jadi tidak mungkin saldo
berubah tanpa ada catatannya.
"""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse

from database import ambil_satu, ambil_semua, get_db, jalankan
from helper import (
    SQL_TRANSAKSI,
    Alihkan,
    alihkan,
    khusus_pengguna,
    pesan,
    render,
    rupiah,
    user_login,
)

router = APIRouter()

# Batas nominal (minimal, maksimal) untuk tiap jenis transaksi.
BATAS = {
    "topup": (10_000, 2_000_000),
    "kirim": (1_000, 2_000_000),
    "bayar": (1_000, 2_000_000),
}


def periksa_nominal(jenis, nominal):
    """Kembalikan teks kesalahan, atau None kalau nominal masih dalam batas."""
    kecil, besar = BATAS[jenis]
    if not kecil <= nominal <= besar:
        return f"Nominal harus antara {rupiah(kecil)} dan {rupiah(besar)}."
    return None


# ---------- Isi saldo ----------

@router.get("/topup")
def form_topup(request: Request, user=Depends(khusus_pengguna), db=Depends(get_db)):
    metode = ambil_semua(db, "SELECT * FROM metode_topup WHERE aktif ORDER BY nama_metode")
    return render(request, "topup.html", user, metode=metode, batas=BATAS["topup"])


@router.post("/topup")
def topup(
    request: Request,
    metode_id: int = Form(...),
    nominal: int = Form(...),
    user=Depends(khusus_pengguna),
    db=Depends(get_db),
):
    salah = periksa_nominal("topup", nominal)
    if not salah and not ambil_satu(
        db, "SELECT id FROM metode_topup WHERE id = %s AND aktif", (metode_id,)
    ):
        salah = "Metode isi saldo tidak tersedia."
    if salah:
        pesan(request, salah, "gagal")
        return alihkan("/topup")

    saldo = jalankan(
        db,
        "UPDATE pengguna SET saldo = saldo + %s WHERE id = %s RETURNING saldo",
        (nominal, user["id"]),
    )["saldo"]
    baru = jalankan(
        db,
        """
        INSERT INTO transaksi (pengguna_id, jenis, metode_id, nominal, saldo_akhir)
        VALUES (%s, 'topup', %s, %s, %s)
        RETURNING id
        """,
        (user["id"], metode_id, nominal, saldo),
    )
    db.commit()

    pesan(request, f"Isi saldo {rupiah(nominal)} berhasil.")
    return alihkan(f"/transaksi/{baru['id']}")


# ---------- Kirim saldo ke pengguna lain ----------

@router.get("/kirim")
def form_kirim(request: Request, user=Depends(khusus_pengguna)):
    return render(request, "kirim.html", user, batas=BATAS["kirim"])


@router.get("/kirim/cek")
def cek_penerima(no_hp: str = "", user=Depends(khusus_pengguna), db=Depends(get_db)):
    """Dipanggil JavaScript di form Kirim untuk menampilkan nama pemilik nomor HP."""
    no_hp = no_hp.strip()[:15]
    penerima = ambil_satu(
        db,
        "SELECT id, nama FROM pengguna WHERE no_hp = %s AND aktif AND role = 'pengguna'",
        (no_hp,),
    )
    if not penerima:
        return JSONResponse({"ada": False, "teks": "Nomor HP belum terdaftar."})
    if penerima["id"] == user["id"]:
        return JSONResponse({"ada": False, "teks": "Itu nomor Anda sendiri."})
    return JSONResponse({"ada": True, "teks": f"Penerima: {penerima['nama']}"})


@router.post("/kirim")
def kirim(
    request: Request,
    no_hp: str = Form(...),
    nominal: int = Form(...),
    catatan: str = Form(""),
    user=Depends(khusus_pengguna),
    db=Depends(get_db),
):
    catatan = catatan.strip()[:100] or None
    penerima = ambil_satu(
        db,
        "SELECT id, nama FROM pengguna WHERE no_hp = %s AND aktif AND role = 'pengguna'",
        (no_hp.strip()[:15],),
    )

    salah = periksa_nominal("kirim", nominal)
    if not salah and not penerima:
        salah = "Nomor HP penerima tidak terdaftar."
    if not salah and penerima["id"] == user["id"]:
        salah = "Tidak bisa kirim saldo ke diri sendiri."
    if salah:
        pesan(request, salah, "gagal")
        return alihkan("/kirim")

    # Kunci baris pengirim dan penerima sesuai urutan id. Tanpa ini, dua orang yang
    # saling mengirim pada detik yang sama bisa membuat database deadlock.
    ambil_semua(
        db,
        "SELECT id FROM pengguna WHERE id IN (%s, %s) ORDER BY id FOR UPDATE",
        (user["id"], penerima["id"]),
    )

    # Saldo pengirim hanya dikurangi kalau cukup (syarat saldo >= nominal).
    pengirim = jalankan(
        db,
        "UPDATE pengguna SET saldo = saldo - %s WHERE id = %s AND saldo >= %s RETURNING saldo",
        (nominal, user["id"], nominal),
    )
    if not pengirim:
        db.rollback()
        pesan(request, "Saldo tidak cukup.", "gagal")
        return alihkan("/kirim")

    saldo_penerima = jalankan(
        db,
        "UPDATE pengguna SET saldo = saldo + %s WHERE id = %s RETURNING saldo",
        (nominal, penerima["id"]),
    )["saldo"]
    baru = jalankan(
        db,
        """
        INSERT INTO transaksi (pengguna_id, jenis, lawan_id, nominal, saldo_akhir, catatan)
        VALUES (%s, 'kirim', %s, %s, %s, %s)
        RETURNING id
        """,
        (user["id"], penerima["id"], nominal, pengirim["saldo"], catatan),
    )
    jalankan(
        db,
        """
        INSERT INTO transaksi (pengguna_id, jenis, lawan_id, nominal, saldo_akhir, catatan)
        VALUES (%s, 'terima', %s, %s, %s, %s)
        """,
        (penerima["id"], user["id"], nominal, saldo_penerima, catatan),
    )
    db.commit()

    pesan(request, f"Kirim {rupiah(nominal)} ke {penerima['nama']} berhasil.")
    return alihkan(f"/transaksi/{baru['id']}")


# ---------- Bayar layanan ----------

@router.get("/bayar")
def form_bayar(request: Request, user=Depends(khusus_pengguna), db=Depends(get_db)):
    layanan = ambil_semua(
        db,
        """
        SELECT l.id, l.nama_layanan, l.biaya_admin, k.nama_kategori
        FROM layanan l
        JOIN kategori k ON k.id = l.kategori_id
        WHERE l.aktif
        ORDER BY k.nama_kategori, l.nama_layanan
        """,
    )
    return render(request, "bayar.html", user, layanan=layanan, batas=BATAS["bayar"])


@router.post("/bayar")
def bayar(
    request: Request,
    layanan_id: int = Form(...),
    nominal: int = Form(...),
    nomor_tujuan: str = Form(""),
    catatan: str = Form(""),
    user=Depends(khusus_pengguna),
    db=Depends(get_db),
):
    nomor_tujuan = nomor_tujuan.strip()[:30] or None
    catatan = catatan.strip()[:100] or None

    salah = periksa_nominal("bayar", nominal)
    layanan = None
    if not salah:
        layanan = ambil_satu(
            db,
            "SELECT id, nama_layanan, biaya_admin FROM layanan WHERE id = %s AND aktif",
            (layanan_id,),
        )
        if not layanan:
            salah = "Layanan tidak tersedia."
    if salah:
        pesan(request, salah, "gagal")
        return alihkan("/bayar")

    total = nominal + layanan["biaya_admin"]
    pembayar = jalankan(
        db,
        "UPDATE pengguna SET saldo = saldo - %s WHERE id = %s AND saldo >= %s RETURNING saldo",
        (total, user["id"], total),
    )
    if not pembayar:
        db.rollback()
        pesan(request, f"Saldo tidak cukup. Total yang dibutuhkan {rupiah(total)}.", "gagal")
        return alihkan("/bayar")

    baru = jalankan(
        db,
        """
        INSERT INTO transaksi
            (pengguna_id, jenis, layanan_id, nomor_tujuan, nominal, biaya_admin, saldo_akhir, catatan)
        VALUES (%s, 'bayar', %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            user["id"], layanan["id"], nomor_tujuan, nominal,
            layanan["biaya_admin"], pembayar["saldo"], catatan,
        ),
    )
    db.commit()

    pesan(request, f"Pembayaran {layanan['nama_layanan']} sebesar {rupiah(total)} berhasil.")
    return alihkan(f"/transaksi/{baru['id']}")


# ---------- Bukti transaksi (struk) ----------

@router.get("/transaksi/{id}")
def bukti_transaksi(id: int, request: Request, user=Depends(user_login), db=Depends(get_db)):
    """Pengguna hanya bisa membuka bukti transaksinya sendiri. Admin bisa semua."""
    if not 0 < id < 2_147_483_647:
        raise Alihkan("/laporan/mutasi", "Transaksi tidak ditemukan.")
    t = ambil_satu(db, SQL_TRANSAKSI + " WHERE t.id = %s", (id,))
    if not t or (user["role"] != "admin" and t["pengguna_id"] != user["id"]):
        raise Alihkan("/laporan/mutasi", "Transaksi tidak ditemukan.")
    return render(request, "struk.html", user, t=t)
