"""File master (khusus admin): kategori, layanan, metode isi saldo, dan pengguna."""
from fastapi import APIRouter, Depends, Form, Request
from psycopg2 import IntegrityError
from psycopg2.errors import ForeignKeyViolation, UniqueViolation

from database import ambil_satu, ambil_semua, get_db, jalankan
from helper import (
    Alihkan,
    alihkan,
    hash_password,
    khusus_admin,
    periksa_data_diri,
    periksa_email,
    periksa_password,
    periksa_teks,
    pesan,
    render,
    rupiah,
)

router = APIRouter(prefix="/admin")

BIAYA_ADMIN_MAKS = 100_000


def simpan(request, db, sql, params, url, salah=None, url_form=None):
    """Jalankan INSERT atau UPDATE data master, lalu kembali ke halaman daftar.

    Kalau isian salah (salah berisi teks), data tidak disimpan dan pengguna
    dikembalikan ke form supaya bisa memperbaiki.
    """
    if salah:
        pesan(request, salah, "gagal")
        return alihkan(url_form or url)
    try:
        jalankan(db, sql, params)
        db.commit()
        pesan(request, "Data berhasil disimpan.")
    except UniqueViolation:
        db.rollback()
        pesan(request, "Gagal disimpan: nama, email, atau nomor itu sudah dipakai.", "gagal")
        return alihkan(url_form or url)
    except IntegrityError:
        db.rollback()
        pesan(request, "Gagal disimpan: data yang dipilih tidak valid.", "gagal")
        return alihkan(url_form or url)
    return alihkan(url)


def hapus(request, db, tabel, id, url):
    """Hapus satu baris data master. Ditolak kalau datanya masih dipakai tabel lain."""
    try:
        baris = jalankan(db, f"DELETE FROM {tabel} WHERE id = %s RETURNING id", (id,))
        db.commit()
        if baris:
            pesan(request, "Data berhasil dihapus.")
        else:
            pesan(request, "Data tidak ditemukan.", "gagal")
    except ForeignKeyViolation:
        db.rollback()
        pesan(
            request,
            "Tidak bisa dihapus karena sudah dipakai di data lain. Nonaktifkan saja.",
            "gagal",
        )
    return alihkan(url)


def cari(db, tabel, id, url):
    """Ambil satu baris untuk form edit. Kalau tidak ada, kembali ke halaman daftar."""
    baris = ambil_satu(db, f"SELECT * FROM {tabel} WHERE id = %s", (id,))
    if not baris:
        raise Alihkan(url, "Data tidak ditemukan.")
    return baris


def periksa_biaya(biaya_admin):
    if not 0 <= biaya_admin <= BIAYA_ADMIN_MAKS:
        return f"Biaya admin harus antara Rp 0 dan {rupiah(BIAYA_ADMIN_MAKS)}."
    return None


# ---------- Kategori ----------

@router.get("/kategori")
def daftar_kategori(request: Request, admin=Depends(khusus_admin), db=Depends(get_db)):
    data = ambil_semua(
        db,
        """
        SELECT k.*, COUNT(l.id) AS jumlah_layanan
        FROM kategori k
        LEFT JOIN layanan l ON l.kategori_id = k.id
        GROUP BY k.id
        ORDER BY k.nama_kategori
        """,
    )
    return render(request, "admin/kategori.html", admin, data=data)


@router.get("/kategori/tambah")
def form_tambah_kategori(request: Request, admin=Depends(khusus_admin)):
    return render(request, "admin/kategori_form.html", admin, item=None)


@router.post("/kategori/tambah")
def tambah_kategori(
    request: Request,
    nama_kategori: str = Form(...),
    deskripsi: str = Form(""),
    admin=Depends(khusus_admin),
    db=Depends(get_db),
):
    nama_kategori, deskripsi = nama_kategori.strip(), deskripsi.strip()
    salah = periksa_teks(nama_kategori, "Nama kategori", 50) or periksa_teks(
        deskripsi, "Deskripsi", 200, wajib=False
    )
    return simpan(
        request, db,
        "INSERT INTO kategori (nama_kategori, deskripsi) VALUES (%s, %s)",
        (nama_kategori, deskripsi or None),
        "/admin/kategori", salah, request.url.path,
    )


@router.get("/kategori/{id}/edit")
def form_edit_kategori(
    id: int, request: Request, admin=Depends(khusus_admin), db=Depends(get_db)
):
    item = cari(db, "kategori", id, "/admin/kategori")
    return render(request, "admin/kategori_form.html", admin, item=item)


@router.post("/kategori/{id}/edit")
def edit_kategori(
    id: int,
    request: Request,
    nama_kategori: str = Form(...),
    deskripsi: str = Form(""),
    admin=Depends(khusus_admin),
    db=Depends(get_db),
):
    nama_kategori, deskripsi = nama_kategori.strip(), deskripsi.strip()
    salah = periksa_teks(nama_kategori, "Nama kategori", 50) or periksa_teks(
        deskripsi, "Deskripsi", 200, wajib=False
    )
    return simpan(
        request, db,
        "UPDATE kategori SET nama_kategori = %s, deskripsi = %s WHERE id = %s",
        (nama_kategori, deskripsi or None, id),
        "/admin/kategori", salah, request.url.path,
    )


@router.post("/kategori/{id}/hapus")
def hapus_kategori(
    id: int, request: Request, admin=Depends(khusus_admin), db=Depends(get_db)
):
    return hapus(request, db, "kategori", id, "/admin/kategori")


# ---------- Layanan ----------

@router.get("/layanan")
def daftar_layanan(
    request: Request, q: str = "", admin=Depends(khusus_admin), db=Depends(get_db)
):
    data = ambil_semua(
        db,
        """
        SELECT l.*, k.nama_kategori,
               (SELECT COUNT(*) FROM transaksi t WHERE t.layanan_id = l.id) AS jumlah_transaksi
        FROM layanan l
        JOIN kategori k ON k.id = l.kategori_id
        WHERE l.nama_layanan ILIKE %s OR k.nama_kategori ILIKE %s
        ORDER BY k.nama_kategori, l.nama_layanan
        """,
        (f"%{q}%", f"%{q}%"),
    )
    return render(request, "admin/layanan.html", admin, data=data, q=q)


@router.get("/layanan/tambah")
def form_tambah_layanan(request: Request, admin=Depends(khusus_admin), db=Depends(get_db)):
    kategori = ambil_semua(db, "SELECT * FROM kategori ORDER BY nama_kategori")
    if not kategori:
        raise Alihkan("/admin/kategori", "Buat minimal satu kategori dulu sebelum menambah layanan.")
    return render(request, "admin/layanan_form.html", admin, item=None, kategori=kategori)


@router.post("/layanan/tambah")
def tambah_layanan(
    request: Request,
    nama_layanan: str = Form(...),
    kategori_id: int = Form(...),
    biaya_admin: int = Form(0),
    admin=Depends(khusus_admin),
    db=Depends(get_db),
):
    nama_layanan = nama_layanan.strip()
    salah = periksa_teks(nama_layanan, "Nama layanan", 100) or periksa_biaya(biaya_admin)
    return simpan(
        request, db,
        "INSERT INTO layanan (nama_layanan, kategori_id, biaya_admin) VALUES (%s, %s, %s)",
        (nama_layanan, kategori_id, biaya_admin),
        "/admin/layanan", salah, request.url.path,
    )


@router.get("/layanan/{id}/edit")
def form_edit_layanan(
    id: int, request: Request, admin=Depends(khusus_admin), db=Depends(get_db)
):
    item = cari(db, "layanan", id, "/admin/layanan")
    kategori = ambil_semua(db, "SELECT * FROM kategori ORDER BY nama_kategori")
    return render(request, "admin/layanan_form.html", admin, item=item, kategori=kategori)


@router.post("/layanan/{id}/edit")
def edit_layanan(
    id: int,
    request: Request,
    nama_layanan: str = Form(...),
    kategori_id: int = Form(...),
    biaya_admin: int = Form(0),
    aktif: bool = Form(False),
    admin=Depends(khusus_admin),
    db=Depends(get_db),
):
    nama_layanan = nama_layanan.strip()
    salah = periksa_teks(nama_layanan, "Nama layanan", 100) or periksa_biaya(biaya_admin)
    return simpan(
        request, db,
        """
        UPDATE layanan
        SET nama_layanan = %s, kategori_id = %s, biaya_admin = %s, aktif = %s
        WHERE id = %s
        """,
        (nama_layanan, kategori_id, biaya_admin, aktif, id),
        "/admin/layanan", salah, request.url.path,
    )


@router.post("/layanan/{id}/hapus")
def hapus_layanan(
    id: int, request: Request, admin=Depends(khusus_admin), db=Depends(get_db)
):
    return hapus(request, db, "layanan", id, "/admin/layanan")


# ---------- Metode isi saldo ----------

@router.get("/metode")
def daftar_metode(request: Request, admin=Depends(khusus_admin), db=Depends(get_db)):
    data = ambil_semua(
        db,
        """
        SELECT m.*,
               (SELECT COUNT(*) FROM transaksi t WHERE t.metode_id = m.id) AS jumlah_transaksi
        FROM metode_topup m
        ORDER BY m.nama_metode
        """,
    )
    return render(request, "admin/metode.html", admin, data=data)


@router.get("/metode/tambah")
def form_tambah_metode(request: Request, admin=Depends(khusus_admin)):
    return render(request, "admin/metode_form.html", admin, item=None)


@router.post("/metode/tambah")
def tambah_metode(
    request: Request,
    nama_metode: str = Form(...),
    keterangan: str = Form(""),
    admin=Depends(khusus_admin),
    db=Depends(get_db),
):
    nama_metode, keterangan = nama_metode.strip(), keterangan.strip()
    salah = periksa_teks(nama_metode, "Nama metode", 50) or periksa_teks(
        keterangan, "Keterangan", 200, wajib=False
    )
    return simpan(
        request, db,
        "INSERT INTO metode_topup (nama_metode, keterangan) VALUES (%s, %s)",
        (nama_metode, keterangan or None),
        "/admin/metode", salah, request.url.path,
    )


@router.get("/metode/{id}/edit")
def form_edit_metode(
    id: int, request: Request, admin=Depends(khusus_admin), db=Depends(get_db)
):
    item = cari(db, "metode_topup", id, "/admin/metode")
    return render(request, "admin/metode_form.html", admin, item=item)


@router.post("/metode/{id}/edit")
def edit_metode(
    id: int,
    request: Request,
    nama_metode: str = Form(...),
    keterangan: str = Form(""),
    aktif: bool = Form(False),
    admin=Depends(khusus_admin),
    db=Depends(get_db),
):
    nama_metode, keterangan = nama_metode.strip(), keterangan.strip()
    salah = periksa_teks(nama_metode, "Nama metode", 50) or periksa_teks(
        keterangan, "Keterangan", 200, wajib=False
    )
    return simpan(
        request, db,
        "UPDATE metode_topup SET nama_metode = %s, keterangan = %s, aktif = %s WHERE id = %s",
        (nama_metode, keterangan or None, aktif, id),
        "/admin/metode", salah, request.url.path,
    )


@router.post("/metode/{id}/hapus")
def hapus_metode(
    id: int, request: Request, admin=Depends(khusus_admin), db=Depends(get_db)
):
    return hapus(request, db, "metode_topup", id, "/admin/metode")


# ---------- Pengguna ----------

@router.get("/pengguna")
def daftar_pengguna(
    request: Request, q: str = "", admin=Depends(khusus_admin), db=Depends(get_db)
):
    data = ambil_semua(
        db,
        """
        SELECT id, nama, email, no_hp, role, saldo, aktif, dibuat_pada
        FROM pengguna
        WHERE nama ILIKE %s OR email ILIKE %s OR no_hp ILIKE %s
        ORDER BY role, nama
        """,
        (f"%{q}%", f"%{q}%", f"%{q}%"),
    )
    return render(request, "admin/pengguna.html", admin, data=data, q=q)


@router.get("/pengguna/tambah")
def form_tambah_pengguna(request: Request, admin=Depends(khusus_admin)):
    return render(request, "admin/pengguna_tambah.html", admin)


@router.post("/pengguna/tambah")
def tambah_pengguna(
    request: Request,
    nama: str = Form(...),
    email: str = Form(...),
    no_hp: str = Form(...),
    role: str = Form("pengguna"),
    password: str = Form(...),
    ulangi: str = Form(...),
    admin=Depends(khusus_admin),
    db=Depends(get_db),
):
    nama, email, no_hp = nama.strip(), email.strip().lower(), no_hp.strip()
    salah = (
        periksa_data_diri(nama, no_hp)
        or periksa_email(email)
        or periksa_password(password, ulangi)
        or (None if role in ("admin", "pengguna") else "Peran tidak valid.")
    )
    return simpan(
        request, db,
        "INSERT INTO pengguna (nama, email, no_hp, password, role) VALUES (%s, %s, %s, %s, %s)",
        (nama, email, no_hp, hash_password(password) if not salah else "", role),
        "/admin/pengguna", salah, request.url.path,
    )


@router.get("/pengguna/{id}/edit")
def form_edit_pengguna(
    id: int, request: Request, admin=Depends(khusus_admin), db=Depends(get_db)
):
    item = cari(db, "pengguna", id, "/admin/pengguna")
    return render(request, "admin/pengguna_form.html", admin, item=item)


@router.post("/pengguna/{id}/edit")
def edit_pengguna(
    id: int,
    request: Request,
    nama: str = Form(...),
    no_hp: str = Form(...),
    aktif: bool = Form(False),
    password_baru: str = Form(""),
    admin=Depends(khusus_admin),
    db=Depends(get_db),
):
    nama, no_hp = nama.strip(), no_hp.strip()
    if id == admin["id"]:
        aktif = True  # admin tidak bisa menonaktifkan akunnya sendiri

    salah = periksa_data_diri(nama, no_hp)
    if not salah and password_baru:
        salah = periksa_password(password_baru, password_baru)
    if password_baru and not salah:
        sql = "UPDATE pengguna SET nama = %s, no_hp = %s, aktif = %s, password = %s WHERE id = %s"
        params = (nama, no_hp, aktif, hash_password(password_baru), id)
    else:
        sql = "UPDATE pengguna SET nama = %s, no_hp = %s, aktif = %s WHERE id = %s"
        params = (nama, no_hp, aktif, id)
    return simpan(request, db, sql, params, "/admin/pengguna", salah, request.url.path)


@router.post("/pengguna/{id}/hapus")
def hapus_pengguna(
    id: int, request: Request, admin=Depends(khusus_admin), db=Depends(get_db)
):
    if id == admin["id"]:
        pesan(request, "Akun sendiri tidak bisa dihapus.", "gagal")
        return alihkan("/admin/pengguna")
    sisa = ambil_satu(db, "SELECT saldo FROM pengguna WHERE id = %s", (id,))
    if sisa and sisa["saldo"] > 0:
        pesan(request, "Pengguna yang masih punya saldo tidak bisa dihapus. Nonaktifkan saja.", "gagal")
        return alihkan("/admin/pengguna")
    return hapus(request, db, "pengguna", id, "/admin/pengguna")
