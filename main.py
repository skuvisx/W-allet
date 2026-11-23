"""W-allet: dompet digital sederhana (FastAPI + Jinja2 + PostgreSQL).

Menjalankan di laptop:
    python -m uvicorn main:app --reload
"""
import logging
import os

import psycopg2
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from helper import BASE_DIR, NAMA_APLIKASI, Alihkan, pesan, templates
from routers import (
    auth_router,
    dashboard_router,
    laporan_router,
    master_router,
    transaksi_router,
)

log = logging.getLogger("w-allet")

# Render atau Vercel selalu mengisi variabel RENDER / VERCEL. Di sana situs memakai HTTPS,
# jadi cookie login hanya dikirim lewat HTTPS supaya lebih aman.
DI_HOSTING = bool(os.getenv("RENDER") or os.getenv("VERCEL"))

app = FastAPI(title=NAMA_APLIKASI, docs_url=None, redoc_url=None, openapi_url=None)

# Session login disimpan di cookie yang ditandatangani dengan SECRET_KEY.
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "ganti-kunci-ini-saat-hosting"),
    max_age=60 * 60 * 8,  # login berlaku 8 jam
    same_site="lax",
    https_only=DI_HOSTING,
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ---------- Penanganan error: tidak ada halaman JSON mentah atau crash ----------

def halaman_error(request, kode, judul, teks):
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={"user": None, "pesan": None, "kode": kode, "judul": judul, "teks": teks},
        status_code=kode,
    )


@app.exception_handler(Alihkan)
def tangani_alihkan(request: Request, exc: Alihkan):
    if exc.teks:
        pesan(request, exc.teks, "gagal")
    return RedirectResponse(exc.url, status_code=303)


@app.exception_handler(RequestValidationError)
def tangani_isian_salah(request: Request, exc: RequestValidationError):
    """Isian form tidak sesuai tipe (misalnya nominal berisi huruf atau kosong).

    Form POST dikembalikan ke halaman form dengan pesan. Alamat GET yang salah
    (misalnya /admin/kategori/abc/edit) dianggap halaman tidak ditemukan.
    """
    jalur = request.url.path
    if request.method == "POST":
        pesan(request, "Isian tidak valid. Periksa kembali angka dan kolom wajib.", "gagal")
        if jalur.endswith("/hapus"):
            jalur = jalur.rsplit("/", 2)[0]
        return RedirectResponse(jalur, status_code=303)
    return halaman_error(request, 404, "Halaman tidak ditemukan", "Alamat yang dibuka tidak benar.")


@app.exception_handler(psycopg2.DataError)
def tangani_data_db(request: Request, exc: psycopg2.DataError):
    """Angka atau teks di luar batas kolom database (misalnya id yang terlalu besar)."""
    if request.method == "POST":
        return tangani_isian_salah(request, exc)
    return halaman_error(request, 404, "Halaman tidak ditemukan", "Alamat yang dibuka tidak benar.")


@app.exception_handler(StarletteHTTPException)
def tangani_http(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return halaman_error(request, 404, "Halaman tidak ditemukan",
                             "Halaman yang Anda cari tidak ada atau sudah dipindah.")
    if exc.status_code == 405:
        return halaman_error(request, 405, "Cara akses tidak diizinkan",
                             "Halaman ini tidak bisa dibuka dengan cara tersebut.")
    return halaman_error(request, exc.status_code, "Terjadi kesalahan", str(exc.detail))


@app.exception_handler(Exception)
def tangani_error_server(request: Request, exc: Exception):
    """Error tak terduga (misalnya database tidak bisa dihubungi). Detail dicatat di log server."""
    log.exception("Error tak terduga pada %s %s", request.method, request.url.path)
    return halaman_error(
        request, 500, "Terjadi kesalahan di server",
        "Permintaan belum bisa diproses. Coba muat ulang halaman beberapa saat lagi.",
    )


@app.get("/health", include_in_schema=False)
def health():
    """Dipakai Render untuk memeriksa aplikasi masih hidup."""
    return {"status": "ok"}


app.include_router(auth_router.router)
app.include_router(dashboard_router.router)
app.include_router(transaksi_router.router)
app.include_router(master_router.router)
app.include_router(laporan_router.router)
