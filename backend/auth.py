"""
auth.py — Login admin (1 akun: atasan/pemilik) dengan SQLite.
- Password di-hash PBKDF2 (hash di sini HANYA untuk keamanan login,
  BUKAN bagian dari desain deteksi keaslian watermark).
- Sesi: token acak + expire (default 12 jam), dikirim via cookie HttpOnly.
"""
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta

from database import get_conn

SESSION_HOURS = 12

_PBKDF2_ITER = 200_000


# ---------- HASH & VERIFIKASI PASSWORD ----------
def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITER)
    return f"pbkdf2_sha256${_PBKDF2_ITER}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt_hex, dk_hex = stored.split("$")
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters))
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


# ---------- SESI ----------
def create_session(username: str) -> str:
    token = secrets.token_hex(32)
    expires = (datetime.utcnow() + timedelta(hours=SESSION_HOURS)).isoformat()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row is None:
            raise ValueError("User tidak ditemukan")
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, row["id"], expires),
        )
    return token


def get_user_by_token(token: str) -> str | None:
    """Return username jika token valid & belum expire, selain itu None."""
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT u.username FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ? AND s.expires_at > ?
            """,
            (token, datetime.utcnow().isoformat()),
        ).fetchone()
        return row["username"] if row else None


def delete_session(token: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


# ---------- SEED AKUN ADMIN ----------
def create_admin_if_missing():
    """Buat akun admin dari .env bila belum ada.
    GANTI E_RECEIPT_ADMIN_USERNAME / E_RECEIPT_ADMIN_PASSWORD di file .env!
    """
    username = os.environ.get("E_RECEIPT_ADMIN_USERNAME", "admin")
    password = os.environ.get("E_RECEIPT_ADMIN_PASSWORD", "admin123")
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, hash_password(password)),
            )
            print(f"✔ Akun admin dibuat: '{username}'")
            if os.environ.get("E_RECEIPT_ADMIN_PASSWORD") is None:
                print("  ⚠ PASSWORD MASIH DEFAULT 'admin123' — ganti di .env sebelum demo!")
