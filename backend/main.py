"""
main.py — Web API Sistem Deteksi Keabsahan E-Receipt (FastAPI).

Jalankan (dari folder backend):
    uvicorn main:app --reload --port 8000
atau langsung:
    python main.py

Mode demo sidang (setelah `npm run build` di frontend):
    FastAPI otomatis menyajikan halaman React → buka http://localhost:8000
"""
import base64
import os
from pathlib import Path

import cv2
import numpy as np
from dotenv import load_dotenv
from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import auth
import stego_core as core
from database import get_conn, init_db

load_dotenv(Path(__file__).resolve().parent / ".env")   # .env folder backend (kunci server, akun admin)

COOKIE_NAME = "ereceipt_session"
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

app = FastAPI(title="Sistem Deteksi Keabsahan E-Receipt")

# CORS hanya untuk mode development (Vite di port 5173).
# Setelah build, halaman disajikan dari FastAPI sendiri → same-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ AUTENTIKASI ============
def current_user(session: str | None = Cookie(alias=COOKIE_NAME, default=None)) -> str:
    """Dependency: return username jika cookie sesi valid, else 401."""
    if session:
        user = auth.get_user_by_token(session)
        if user:
            return user
    raise HTTPException(status_code=401, detail="Harus login dulu")


@app.post("/api/auth/login")
def login(body: dict):
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
    if row is None or not auth.verify_password(password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Username atau password salah")

    token = auth.create_session(username)
    resp = JSONResponse({"ok": True, "username": username})
    resp.set_cookie(
        COOKIE_NAME, token,
        httponly=True, samesite="lax", max_age=auth.SESSION_HOURS * 3600,
    )
    return resp


@app.post("/api/auth/logout")
def logout(session: str | None = Cookie(alias=COOKIE_NAME, default=None)):
    if session:
        auth.delete_session(session)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE_NAME)
    return resp


@app.get("/api/auth/me")
def me(user: str = Depends(current_user)):
    return {"username": user}


# ============ VERIFIKASI (publik) ============
@app.post("/api/verify")
async def verify(file: UploadFile = File(...)):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="File kosong")
    status, detail = core.verify_seal_bytes(data, file.filename or "")
    return {"status": status, "detail": detail}


# ============ GENERATOR (wajib login) ============
@app.post("/api/generate")
async def generate(
    file: UploadFile = File(...),
    pesan: str = Form(...),
    user: str = Depends(current_user),
):
    pesan = pesan.strip()
    if not pesan:
        raise HTTPException(status_code=400, detail="Pesan tidak boleh kosong")

    # Validasi berbasis BYTE (UTF-8), bukan jumlah karakter: kapasitas sisip
    # juga diukur dalam byte, dan satu karakter non-ASCII bisa 2-4 byte.
    nbyte = core.panjang_byte(pesan)
    maks  = core.kapasitas_pesan()
    if nbyte > maks:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Pesan terlalu panjang: {nbyte} byte (UTF-8) melebihi "
                f"kapasitas maksimum {maks} byte"
            ),
        )

    data = await file.read()
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="File bukan gambar yang valid")

    try:
        img_seal, stats = core.generate_seal(img, pesan)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    bmp_b64 = base64.b64encode(core.encode_bmp_bytes(img_seal)).decode("ascii")
    return {
        "status": "ok",
        "bmp_base64": bmp_b64,
        "stats": stats,
        "generator": user,
        "kapasitas": {"maks_byte": maks, "terpakai_byte": nbyte},
    }


# ============ STATIC: halaman React hasil build ============
if FRONTEND_DIST.exists():
    assets = FRONTEND_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")
    for fav in ("favicon.ico", "vite.svg"):
        p = FRONTEND_DIST / fav
        if p.exists():

            @app.get(f"/{fav}", include_in_schema=False)
            def _fav():
                return FileResponse(p)


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    """SPA fallback: semua route non-API → index.html (jika sudah di-build)."""
    index = FRONTEND_DIST / "index.html"
    if not index.exists():
        return JSONResponse(
            {"pesan": "Frontend belum di-build. Jalankan `npm run build` di folder frontend."},
            status_code=404,
        )
    return FileResponse(index)


@app.on_event("startup")
def _startup():
    # Kunci server diperiksa & diturunkan sekali di awal (fail-fast).
    # Kalau E_RECEIPT_SECRET_KEY belum diatur, server langsung berhenti
    # dengan pesan jelas, bukan diam-diam memakai kunci bawaan.
    try:
        core.get_key()
    except RuntimeError as e:
        print("✖ Konfigurasi kunci belum siap:")
        print(" ", e)
        raise
    init_db()
    auth.create_admin_if_missing()
    if FRONTEND_DIST.exists():
        print(f"✔ Frontend tersedia di: {FRONTEND_DIST}")
        print("  Buka http://localhost:8000")
    else:
        print("ℹ Frontend belum di-build — jalankan `npm run build` di folder frontend.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
