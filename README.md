# Sistem Deteksi Keabsahan E-Receipt — Web App

Implementasi web dari sistem deteksi keabsahan e-receipt (skripsi) dengan
**2 fitur**:

| Halaman | Akses | Fungsi |
|---|---|---|
| 🕵️ **Ekstraksi** | Publik (semua orang) | Upload file `.bmp` → status keabsahan + pesan hasil dekripsi |
| 📝 **Generator** | Khusus admin (login) | Upload e-receipt + tulis pesan → seal `.bmp` (unduh) |

## Teknologi

- **Backend**: Python 3.14 · FastAPI · uvicorn · SQLite · OpenCV · cryptography
- **Frontend**: React 19 · Vite 7 · react-router-dom 7

## Struktur

```
web_e_receipt/
├── backend/
│   ├── main.py          # API FastAPI (login, verify, generate, serve frontend)
│   ├── stego_core.py    # Inti steganografi (dipindah dari notebook)
│   ├── auth.py          # Login admin (PBKDF2) + sesi cookie 12 jam
│   ├── database.py      # SQLite: users + sessions
│   ├── .env             # ⚠ GANTI password admin default!
│   └── requirements.txt
├── frontend/            # React SPA
│   ├── src/pages/       # Ekstraksi.jsx · Login.jsx · Generator.jsx
│   └── dist/            # Hasil build (disajikan oleh FastAPI)
└── README.md
```

## Cara Menjalankan

### Mode demo sidang (1 perintah)

```powershell
cd web_e_receipt\backend
python -m uvicorn main:app --port 8000
```

Lalu buka **http://localhost:8000** — FastAPI otomatis menyajikan `frontend/dist`.

### Mode pengembangan (hot reload)

```powershell
# Terminal 1 — backend
cd web_e_receipt\backend
python -m uvicorn main:app --reload --port 8000

# Terminal 2 — frontend
cd web_e_receipt\frontend
npm install
npm run dev          # http://localhost:5173 (proxy /api → :8000)
```

### Setup awal

```powershell
pip install -r web_e_receipt\backend\requirements.txt
cd web_e_receipt\frontend
npm install
npm run build        # sekali saja, agar mode demo berfungsi
```

## Konfigurasi (file `.env` di `backend/`)

| Variabel | Default | Keterangan |
|---|---|---|
| `E_RECEIPT_SECRET_KEY` | *(wajib diisi, tanpa default)* | Passphrase kunci AES-GCM. Diturunkan menjadi kunci 256-bit memakai **PBKDF2-HMAC-SHA256 (200.000 iterasi)**. **Harus sama** dengan notebook agar seal kompatibel |
| `E_RECEIPT_KEY_SALT` | `e-receipt-stego-v1` | *(opsional)* Salt PBKDF2. Bukan data rahasia, tetapi **harus sama** antara generator dan verifier |
| `E_RECEIPT_ADMIN_USERNAME` | `admin` | Username login admin |
| `E_RECEIPT_ADMIN_PASSWORD` | `admin123` | ⚠ **GANTI sebelum demo!** |

> Akun admin dibuat otomatis saat server pertama kali dijalankan. Hapus
> `auth.db` jika ingin reset akun.
> Bila `E_RECEIPT_SECRET_KEY` kosong, server **gagal start** dengan pesan
> jelas (fail-fast) — sengaja tanpa kunci bawaan di kode.

## Catatan Penting

- **Ekstraksi bersifat publik** — verifikasi tidak butuh login.
- **Generator butuh login** — hanya 1 admin (atasan/pemilik) yang menanam pesan.
- **Hash TIDAK dipakai** dalam desain deteksi keaslian (sesuai arahan dosen).
  PBKDF2 hanya untuk keamanan password login **dan untuk menurunkan (key
  derivation) kunci AES dari passphrase server** — keduanya bukan untuk
  memeriksa keaslian dokumen. Keaslian seal berbasis
  **AES-GCM (authenticated encryption) + LSB 2-bit + majority voting**.
- Pesan maksimal ±160 karakter (tergantung ukuran citra; dibatasi 300 di UI).
- Sesi login kedaluwarsa 12 jam (cookie HttpOnly, SameSite=lax).

## Kenapa Tetap Pakai Database Padahal Admin Hanya 1 Orang?

Walaupun sistem hanya memiliki **1 admin** (atasan/pemilik yang berhak
menanam pesan), autentikasi tetap menggunakan **database SQLite**
(`auth.db`) dan tidak cukup hanya mengandalkan file `.env`. Alasannya:

### 1. `.env` hanya sumber kredensial awal, bukan penyimpanan runtime
File `.env` dibaca **satu kali** saat server pertama kali dijalankan untuk
membuat akun admin (password langsung di-hash PBKDF2 sebelum disimpan ke
tabel `users`). Setelah itu, semua proses login berjalan di database.

### 2. Sesi login butuh penyimpanan yang dinamis (tabel `sessions`)
Setiap kali admin login, sistem membuat **token sesi acak** yang disimpan
di tabel `sessions` beserta waktu kedaluwarsanya (12 jam). Token inilah
yang dikirim lewat cookie HttpOnly dan dicek pada setiap permintaan.
File statis tidak dapat menangani penambahan/penghapusan token per login,
apalagi jika admin login dari lebih dari satu perangkat.

### 3. Logout yang benar-benar mematikan sesi
Dengan database, tombol *Keluar* menghapus token dari tabel `sessions` —
sesi langsung tidak valid di sisi server. Tanpa database (misal hanya
mengandalkan token bertanda tangan seperti JWT), logout hanya menghapus
cookie di browser, sedangkan token tetap hidup sampai 12 jam.

### 4. Keamanan password
Password di database tersimpan sebagai **hash** (`pbkdf2_sha256$...`),
bukan teks asli. Sekalipun file `auth.db` bocor, password tidak dapat
dibaca langsung.

### 5. Nilai lebih untuk penulisan skripsi
Keberadaan database memberikan gambaran arsitektur yang lebih lengkap
(tabel `users` dan `sessions` beserta relasinya) dan dapat dijelaskan
dengan bagan pada bab perancangan sistem — sesuatu yang tidak dapat
diperlihatkan jika autentikasi hanya berupa perbandingan teks dengan
file `.env`.

> **Ringkasnya**: `.env` berperan sebagai *pintu masuk pertama* yang
> membekali database dengan kredensial admin, sedangkan database
> menjalankan seluruh mekanisme autentikasi (cek password, kelola sesi,
> logout, dan kedaluwarsa) setiap hari.
