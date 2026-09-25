"""
stego_core.py — Inti sistem deteksi keabsahan e-receipt.
(Dipindah dari notebook sistem_deteksi_e_receipt_v2.ipynb agar bisa
dipakai bareng oleh web & notebook, tanpa duplikasi.)

Alur GENERATOR : pesan rahasia (teks bebas user) → bungkus [2B panjang | utf-8]
                 → AES-GCM → [nonce|ct|tag] → [2B len cipher | cipher]
                 → bit → LSB 2-bit → 4 sudut + grid.
Alur VERIFIER  : gerbang BMP → ekstrak semua salinan → dekripsi (InvalidTag =
                 rusak/kunci salah) → majority voting → ABSAH / TIDAK ABSAH /
                 TIDAK TERVERIFIKASI / DITOLAK (bukan BMP).

CATATAN (penting untuk sidang): sistem ini TANPA fungsi hash untuk keaslian.
Keaslian dijaga oleh AES-GCM (authenticated encryption) + redudansi salinan +
majority voting.

CATATAN KUNCI: PBKDF2-HMAC-SHA256 di sini HANYA dipakai untuk MENURUNKAN kunci
AES-256 dari passphrase server (key derivation, RFC 8018) — bukan untuk
memeriksa keaslian dokumen. Jadi desain "tanpa hash" untuk deteksi keaslian
tetap berlaku.
"""
import hashlib
import os
import time
from collections import Counter

import numpy as np
import cv2
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# ============ PARAMETER SISTEM ============
BITS        = 2   # bit LSB per saluran warna (2 bit × 3 saluran = 6 bit/piksel)
CORNER_SIZE = 40  # ukuran blok sudut (px)
GRID        = 16  # ukuran blok grid (px)

# Overhead bungkusan pesan yang ikut tertanam (byte):
#   2 B panjang pesan asli + 12 B nonce GCM + 16 B tag GCM + 2 B panjang ciphertext
OVERHEAD_BYTES = 2 + 12 + 16 + 2   # = 32 byte

# ============ KUNCI SERVER (AES-256) — DERIVASI PBKDF2 ============
# Kunci TIDAK lagi diambil langsung dari teks passphrase (yang sebelumnya hanya
# di-pad/truncate dengan byte nol), melainkan diturunkan memakai
# PBKDF2-HMAC-SHA256 (RFC 8018) agar setiap percobaan tebakan passphrase
# menjadi jauh lebih mahal, sehingga brute force tidak lagi praktis.
PBKDF2_ITER    = 200_000                 # jumlah iterasi = faktor kerja
PBKDF2_DKLEN   = 32                      # 32 byte = 256 bit → AES-256
SALT_DEFAULT   = "e-receipt-stego-v1"     # salt tetap: WAJIB sama saat generate & verify
MIN_SECRET_LEN = 16                      # di bawah ini hanya diberi peringatan

_KEY_CACHE: dict = {}
_AES_CACHE: dict = {}   # cache objek AESGCM per kunci (menghindari jadwal ulang kunci)


def _aes(key: bytes) -> AESGCM:
    """Objek AESGCM untuk sebuah kunci, dibuat sekali lalu dipakai ulang.

    AESGCM(key) melakukan penjadwalan kunci; membuatnya ribuan kali (sekali per
    blok) hanya membuang waktu karena hasilnya identik untuk kunci yang sama.
    """
    aes = _AES_CACHE.get(key)
    if aes is None:
        aes = _AES_CACHE[key] = AESGCM(key)
    return aes


def _salt_kunci() -> bytes:
    """Salt untuk PBKDF2. Salt bukan data rahasia, tetapi harus KONSISTEN
    (boleh di-override lewat env E_RECEIPT_KEY_SALT bila ingin dipisah)."""
    return os.environ.get("E_RECEIPT_KEY_SALT", SALT_DEFAULT).encode("utf-8")


def get_secret() -> str:
    """Ambil passphrase server dari environment variable.

    Tidak ada fallback yang ditanam di kode: bila belum diatur, sistem langsung
    berhenti dengan pesan yang jelas (fail-fast) agar tidak diam-diam memakai
    kunci default yang tertulis di repositori.
    """
    secret = (os.environ.get("E_RECEIPT_SECRET_KEY") or "").strip()
    if not secret:
        raise RuntimeError(
            "E_RECEIPT_SECRET_KEY belum diatur.\n"
            "  Isi variabel lingkungan ini (atau berkas .env di folder backend) "
            "dengan passphrase kunci server, contoh:\n"
            "    E_RECEIPT_SECRET_KEY=passphrase-panjang-dan-rahasiya-anda"
        )
    if len(secret) < MIN_SECRET_LEN:
        print(
            f"⚠ E_RECEIPT_SECRET_KEY hanya {len(secret)} karakter — disarankan "
            f"minimal {MIN_SECRET_LEN} karakter agar tahan terhadap brute force."
        )
    return secret


def derive_key(secret: str, salt: bytes | str | None = None) -> bytes:
    """Turunkan kunci AES-256 (32 byte) dari passphrase memakai
    PBKDF2-HMAC-SHA256. Salt default diambil dari E_RECEIPT_KEY_SALT."""
    if salt is None:
        salt = _salt_kunci()
    if isinstance(salt, str):
        salt = salt.encode("utf-8")
    return hashlib.pbkdf2_hmac(
        "sha256", secret.encode("utf-8"), salt, PBKDF2_ITER, dklen=PBKDF2_DKLEN
    )


def get_key() -> bytes:
    """Kunci AES-256 hasil derivasi. Dihitung sekali lalu di-cache, sehingga
    PBKDF2 tidak dijalankan berulang pada setiap permintaan verifikasi."""
    if "key" not in _KEY_CACHE:
        _KEY_CACHE["key"] = derive_key(get_secret())
    return _KEY_CACHE["key"]


def __getattr__(name: str):
    """Kompatibilitas: `stego_core.KEY` tetap dapat dipakai seperti sebelumnya
    (nilainya baru dihitung saat atribut diakses)."""
    if name == "KEY":
        return get_key()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ============ PESAN RAHASIA (teks bebas user) ============
def bungkus_pesan(pesan: str) -> bytes:
    """Bungkus pesan rahasia = [2B panjang] + [pesan UTF-8].
    Header 2 byte otomatis disisipkan agar panjang pesan terbaca saat ekstraksi."""
    data = pesan.encode("utf-8")
    n = len(data)
    assert n <= 65535, "Pesan terlalu panjang (maks 65535 byte)"
    return n.to_bytes(2, "big") + data


def baca_pesan(data: bytes) -> str:
    """Membaca kembali pesan rahasia dari data hasil dekripsi."""
    n = int.from_bytes(data[:2], "big")
    return data[2:2 + n].decode("utf-8")


# Alias kompatibilitas (nama lama tetap berfungsi jika dipakai modul lain)
build_payload = bungkus_pesan
parse_payload = baca_pesan


# ============ ENKRIPSI / DEKRIPSI AES-GCM ============
def aesgcm_encrypt(key: bytes, plaintext: bytes) -> bytes:
    """Enkripsi → [nonce 12B | ciphertext | tag 16B]."""
    nonce = os.urandom(12)            # nonce unik per enkripsi
    ct = _aes(key).encrypt(nonce, plaintext, None)
    return nonce + ct


def aesgcm_decrypt(key: bytes, data: bytes) -> bytes:
    """Dekripsi; melempar InvalidTag jika rusak / kunci salah."""
    nonce = data[:12]
    return _aes(key).decrypt(nonce, data[12:], None)


# ============ KAPASITAS & LSB 2 BIT ============
def kapasitas_blok(ukuran: int) -> int:
    """Kapasitas (byte) satu blok ukuran×ukuran dengan LSB 2 bit per saluran."""
    return (ukuran * ukuran * 3 * BITS) // 8


def kapasitas_pesan() -> int:
    """Kapasitas maksimum PESAN (byte) yang bisa disisipkan.

    Blok terkecil adalah blok grid (GRID×GRID), sehingga blok itulah yang
    menentukan batas: seluruh bungkusan pesan (pesan + overhead) harus muat
    di satu blok.
        kapasitas_pesan() = kapasitas_blok(GRID) - OVERHEAD_BYTES
                          = 192 - 32 = 160 byte
    """
    return kapasitas_blok(GRID) - OVERHEAD_BYTES


def panjang_byte(pesan: str) -> int:
    """Panjang pesan dalam BYTE (UTF-8), BUKAN jumlah karakter.

    Penting: kapasitas sisip dihitung dalam byte, sedangkan satu karakter
    non-ASCII (mis. emoji atau huruf beraksen) memakan 2-4 byte. Karena itu
    validasi harus berbasis byte agar tidak ada pesan yang lolos validasi
    tetapi gagal disisipkan.
    """
    return len(pesan.encode("utf-8"))


def bytes_to_bits(data: bytes):
    """Byte → daftar bit (0/1)."""
    return [int(b) for byte in data for b in f"{byte:08b}"]


def bits_to_bytes(bits) -> bytes:
    """Daftar/array bit (0/1) → byte (sisa bit yang tidak genap 8 diabaikan).

    Konversi dilakukan sekaligus di level larik memakai `np.packbits`, bukan
    perulangan Python per bit. Bit pertama menjadi bit paling signifikan,
    sehingga hasilnya sama persis dengan versi perulangan sebelumnya.
    """
    arr = np.asarray(bits, dtype=np.uint8).reshape(-1)
    n = (arr.size // 8) * 8
    return np.packbits(arr[:n], bitorder="big").tobytes()


def embed_bits_blok(img, bits, x0, y0, ukuran):
    """Sisipkan bit ke 2 LSB per saluran (B,G,R) pada blok ukuran×ukuran di (x0,y0).

    Versi vektor: bit dikelompokkan berpasangan (LSB-0, LSB-1) lalu ditulis ke
    seluruh blok sekaligus dengan operasi larik, bukan perulangan piksel.
    Bila jumlah bit ganjil, bit terakhir dipasangkan dengan 0 — sama seperti
    perilaku versi perulangan sebelumnya.
    """
    n = len(bits)
    cap = ukuran * ukuran * 6
    assert n <= cap, f"Blok {ukuran}x{ukuran} hanya muat {cap} bit, butuh {n} bit"

    arr = np.asarray(bits, dtype=np.uint8).reshape(-1)
    pasang = np.zeros((n + 1) // 2 * 2, dtype=np.uint8)
    pasang[:n] = arr
    nilai = pasang[0::2] | (pasang[1::2] << 1)     # 2 bit per (piksel, saluran)

    target = img[y0:y0 + ukuran, x0:x0 + ukuran]
    datar = target.reshape(-1)                     # urutan (baris, kolom, saluran)
    n_tulis = min(nilai.size, datar.size)
    datar[:n_tulis] = (datar[:n_tulis] & 0b11111100) | nilai[:n_tulis]
    target[:] = datar.reshape(ukuran, ukuran, 3)   # tulis balik lewat penampakan (view)


def extract_bits_blok(img, x0, y0, ukuran, nbits):
    """Ekstrak nbits bit pertama dari blok ukuran×ukuran di (x0,y0).

    Pembungkus tipis di atas `bidang_bit` + `bit_blok` (versi vektor) yang
    mempertahankan antarmuka lama; tetap mengembalikan daftar bilangan bulat.
    Untuk pemakaian massal, panggil `bidang_bit` sekali lalu `bit_blok` per blok.
    """
    blok = img[y0:y0 + ukuran, x0:x0 + ukuran]
    return bit_blok(bidang_bit(blok), 0, 0, ukuran, nbits).tolist()


def bidang_bit(citra):
    """Susun LSB seluruh piksel citra menjadi SATU matriks bit berukuran (H, W×6).

    Untuk setiap piksel urutan bitnya adalah saluran B (LSB-0, LSB-1), lalu G,
    lalu R — sama seperti penelusuran piksel baris demi baris pada versi
    perulangan. Seluruh piksel diproses sekaligus dengan operasi larik NumPy,
    sehingga tidak ada perulangan Python per piksel.
    """
    pasangan = np.stack((citra & 1, (citra >> 1) & 1), axis=-1)   # (H, W, 3, 2)
    H, W = citra.shape[:2]
    return pasangan.reshape(H, W * 6).astype(np.uint8)


def bit_blok(bidang, x0, y0, ukuran, nbits):
    """Ambil `nbits` bit pertama dari blok ukuran×ukuran pada (x0,y0).

    `bidang` adalah matriks bit hasil `bidang_bit()`. Pengambilan hanya berupa
    pemotongan larik (slice) sehingga biayanya sangat kecil.
    """
    potong = bidang[y0:y0 + ukuran, x0 * 6:(x0 + ukuran) * 6].reshape(-1)
    # setara dengan `if len(bits) >= nbits: return bits` pada versi perulangan
    n_ambil = min(potong.size, ((nbits + 1) // 2) * 2)
    return np.ascontiguousarray(potong[:n_ambil])


# ============ POSISI BLOK ============
def posisi_sudut(W, H):
    """4 blok sudut CORNER_SIZE×CORNER_SIZE (koordinat kiri-atas tiap sudut)."""
    s = CORNER_SIZE
    return [(0, 0), (W - s, 0), (0, H - s), (W - s, H - s)]


def posisi_grid(W, H):
    """Blok grid GRID×GRID tersebar di seluruh citra,
    TIDAK tumpang-tindih dengan blok sudut (agar salinan sudut tetap utuh)."""
    s, cs = GRID, CORNER_SIZE
    sudut = posisi_sudut(W, H)

    def tabrakan(x, y):
        """True jika kotak grid (x,y,s,s) menabrak salah satu kotak sudut."""
        for cx, cy in sudut:
            if x < cx + cs and x + s > cx and y < cy + cs and y + s > cy:
                return True
        return False

    pos = []
    for y in range(0, H - s + 1, s):
        for x in range(0, W - s + 1, s):
            if not tabrakan(x, y):
                pos.append((x, y))
    return pos


# ============ GENERATOR ============
def generate_seal(img, pesan: str, key=None):
    """Generator: sisipkan pesan terenkripsi ke 4 sudut + grid.

    Return: (img_seal, stats)
      stats = dict(pesan, nbytes_per_salinan, jumlah_sudut, jumlah_grid,
                   total_salinan, waktu, ukuran)
    """
    if key is None:
        key = get_key()              # kunci diambil lazily (bukan saat import)
    t0 = time.time()
    img = img.copy()                 # salin agar citra asli tidak berubah
    H, W = img.shape[:2]

    # 0) citra harus cukup besar untuk memuat empat blok sudut
    if H < CORNER_SIZE or W < CORNER_SIZE:
        raise ValueError(
            f"Citra terlalu kecil ({W}x{H} piksel). Ukuran minimum "
            f"{CORNER_SIZE}x{CORNER_SIZE} piksel karena sistem memerlukan "
            f"empat blok sudut berukuran {CORNER_SIZE}x{CORNER_SIZE} piksel."
        )

    # 1) bungkus pesan rahasia → enkripsi
    pesan_bungkus = bungkus_pesan(pesan)
    cipher        = aesgcm_encrypt(key, pesan_bungkus)
    data_embed = len(cipher).to_bytes(2, "big") + cipher   # [2B len][cipher]
    bits       = bytes_to_bits(data_embed)

    # 2) cek kapasitas (blok terkecil = grid)
    cap_min = kapasitas_blok(GRID)
    nbytes  = len(data_embed)
    if nbytes > cap_min:
        kelebihan = nbytes - cap_min
        raise ValueError(
            f"Pesan terlalu panjang: butuh {nbytes} byte (termasuk {OVERHEAD_BYTES} B "
            f"overhead enkripsi), sedangkan kapasitas maksimum {cap_min} byte "
            f"(pesan maksimum {cap_min - OVERHEAD_BYTES} byte). "
            f"Kurangi sekitar {kelebihan} byte."
        )

    # 3) posisi blok
    ps = posisi_sudut(W, H)
    pg = posisi_grid(W, H)

    # 4) sisipkan salinan identik ke semua blok
    for (x0, y0) in ps:
        embed_bits_blok(img, bits, x0, y0, CORNER_SIZE)
    for (x0, y0) in pg:
        embed_bits_blok(img, bits, x0, y0, GRID)

    dt = time.time() - t0
    stats = {
        "pesan": pesan,
        "nbytes_per_salinan": nbytes,
        "jumlah_sudut": len(ps),
        "jumlah_grid": len(pg),
        "total_salinan": len(ps) + len(pg),
        "waktu": round(dt, 3),
        "ukuran": f"{W}x{H}",
    }
    return img, stats


def encode_bmp_bytes(img) -> bytes:
    """Encode array citra → bytes file BMP (lossless)."""
    ok, buf = cv2.imencode(".bmp", img)
    if not ok:
        raise RuntimeError("Gagal meng-encode citra ke BMP")
    return buf.tobytes()


# ============ VERIFIER ============
def is_bmp_filename(nama: str) -> bool:
    """Cek ekstensi file .bmp."""
    return str(nama).lower().endswith(".bmp")


def verify_seal_bytes(data: bytes, nama: str, key=None, verbose=False):
    """Verifikasi dari bytes file upload (tanpa menyimpan ke disk).

    Return: (status, detail)
      detail = dict(pesan, total_salinan, salinan_ok, blok_rusak, waktu)
    """
    t0 = time.time()
    if not is_bmp_filename(nama) or data[:2] != b"BM":
        return "DITOLAK (bukan BMP)", {
            "pesan": None, "total_salinan": 0, "salinan_ok": 0,
            "blok_rusak": 0, "waktu": round(time.time() - t0, 3),
            "peta_rusak": [],
        }
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return "DITOLAK (bukan BMP)", {
            "pesan": None, "total_salinan": 0, "salinan_ok": 0,
            "blok_rusak": 0, "waktu": round(time.time() - t0, 3),
            "peta_rusak": [],
        }
    if key is None:
        key = get_key()              # dihitung sekali per proses (di-cache)
    return verify_seal_img(img, key=key, verbose=verbose, t0=t0)


def verify_seal_img(img, key=None, verbose=False, t0=None):
    """Inti verifikasi dari array citra BGR (dipakai verify_seal_bytes)."""
    if key is None:
        key = get_key()              # dihitung sebelum timer agar tidak masuk statistik
    if t0 is None:
        t0 = time.time()
    H, W = img.shape[:2]

    # Bidang bit dihitung SEKALI untuk seluruh citra (vektorisasi), bukan
    # berulang-ulang untuk tiap blok seperti pada versi sebelumnya.
    bidang = bidang_bit(img)

    # ===== 1) SUSUN SEMUA SALINAN (4 sudut + grid) =====
    blok = [("sudut", x0, y0, CORNER_SIZE) for (x0, y0) in posisi_sudut(W, H)]
    blok += [("grid", x0, y0, GRID) for (x0, y0) in posisi_grid(W, H)]

    # ===== 2) EKSTRAKSI + DEKRIPSI SETIAP SALINAN =====
    hasil_salinan = []   # (label, x0, y0, uk, ciphertext) BERHASIL didekripsi
    rusak = []           # salinan gagal / berbeda dari mayoritas
    for label, x0, y0, uk in blok:
        cap = kapasitas_blok(uk)
        # Satu kali ekstraksi saja per blok: kapasitas satu blok SELALU cukup
        # untuk memuat [2 B panjang][ciphertext] (karena 16 + n_ct*8 <= 8*cap).
        mentah = bits_to_bytes(bit_blok(bidang, x0, y0, uk, cap * 8))
        # header 2 byte = panjang ciphertext
        n_ct = int.from_bytes(mentah[:2], "big")
        if not (0 < n_ct <= cap - 2):
            rusak.append((label, x0, y0, uk, "header invalid"))
            continue
        cipher = mentah[2:2 + n_ct]
        try:
            aesgcm_decrypt(key, cipher)          # gagal → InvalidTag
            hasil_salinan.append((label, x0, y0, uk, cipher))
        except Exception:
            rusak.append((label, x0, y0, uk, "InvalidTag"))

    # ===== 3) MAJORITY VOTING =====
    if len(hasil_salinan) == 0:
        status = "TIDAK TERVERIFIKASI"
        detail = {
            "pesan": None, "total_salinan": len(blok),
            "salinan_ok": 0, "blok_rusak": len(rusak),
            "waktu": round(time.time() - t0, 3),
            "peta_rusak": [
                {"label": lb, "x": x0, "y": y0, "ukuran": uk}
                for (lb, x0, y0, uk, *_rest) in rusak
            ],
        }
        return status, detail

    suara   = Counter(c for _, _, _, _, c in hasil_salinan)
    pemenang, n_ok = suara.most_common(1)[0]
    n_total = len(blok)

    # salinan yang BEDA dari pemenang → ditandai rusak
    for label, x0, y0, uk, c in hasil_salinan:
        if c != pemenang:
            rusak.append((label, x0, y0, uk, "berbeda"))

    if n_ok == n_total:
        status = "ABSAH"
        pesan = baca_pesan(aesgcm_decrypt(key, pemenang))
    else:
        status = "TIDAK ABSAH"
        pesan = None   # jangan tampilkan pesan dari citra yang rusak

    # koordinat blok yang dimodifikasi (untuk peta lokasi di frontend)
    peta_rusak = [
        {"label": lb, "x": x0, "y": y0, "ukuran": uk}
        for (lb, x0, y0, uk, *_rest) in rusak
    ]
    detail = {
        "pesan": pesan,
        "total_salinan": n_total,
        "salinan_ok": n_ok,
        "blok_rusak": len(rusak),
        "waktu": round(time.time() - t0, 3),
        "peta_rusak": peta_rusak,
    }
    if verbose:
        print(f"Status: {status} | {n_ok}/{n_total} salinan | {len(rusak)} blok rusak")
    return status, detail


# ============ METRIK KUALITAS (untuk info tambahan) ============
def mse(a, b):
    return float(np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2))


def psnr(a, b, maxv=255.0):
    e = mse(a, b)
    return float("inf") if e == 0 else 10.0 * np.log10(maxv ** 2 / e)


def ssim(a, b, win=7, K1=0.01, K2=0.03, L=255.0):
    g1 = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY).astype(np.float64)
    g2 = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY).astype(np.float64)
    C1, C2 = (K1 * L) ** 2, (K2 * L) ** 2
    mu1, mu2 = cv2.blur(g1, (win, win)), cv2.blur(g2, (win, win))
    mu1_2, mu2_2, mu1mu2 = mu1 ** 2, mu2 ** 2, mu1 * mu2
    s1  = cv2.blur(g1 * g1, (win, win)) - mu1_2
    s2  = cv2.blur(g2 * g2, (win, win)) - mu2_2
    s12 = cv2.blur(g1 * g2, (win, win)) - mu1mu2
    atas  = (2 * mu1mu2 + C1) * (2 * s12 + C2)
    bawah = (mu1_2 + mu2_2 + C1) * (s1 + s2 + C2)
    return float(np.mean(atas / bawah))


def ber_lsb(a, b, bits=2):
    """Bit Error Rate: % bit LSB (bits per saluran) yang berbeda antara dua citra."""
    total = a.shape[0] * a.shape[1] * 3 * bits
    beda  = 0
    for c in range(3):
        ac = a[:, :, c].astype(np.int16) & ((1 << bits) - 1)
        bc = b[:, :, c].astype(np.int16) & ((1 << bits) - 1)
        beda += np.count_nonzero(ac != bc) * bits
    return beda / total * 100.0
