import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { authApi, b64ToBlob, upload } from '../api';
import { useAuth } from '../App';
import { IconPen, IconImage, IconShield, IconDownload, IconX, IconFile } from '../components/Icons.jsx';

// Batas pesan dihitung dalam BYTE (UTF-8), bukan jumlah karakter.
// Kapasitas penyisipan = kapasitas blok grid 16x16 (192 B) - overhead 32 B = 160 byte.
// Satu karakter non-ASCII (mis. emoji) bisa memakan 2-4 byte, jadi validasi
// berbasis karakter akan meloloskan pesan yang sebenarnya gagal disegel.
const MAX_BYTE = 160;

const byteLength = (s) => new TextEncoder().encode(s).length;

// Potong teks agar panjang byte-nya tidak melebihi batas (aman untuk emoji).
const potongByte = (s, maks) => {
  if (byteLength(s) <= maks) return s;
  let out = '';
  for (const ch of s) {
    if (byteLength(out + ch) > maks) break;
    out += ch;
  }
  return out;
};

export default function Generator() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [authorized, setAuthorized] = useState(false);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [pesan, setPesan] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [hasil, setHasil] = useState(null);
  const inputRef = useRef(null);

  // Gerbang login: jika bukan admin → redirect ke /login
  useEffect(() => {
    authApi.me()
      .then(() => setAuthorized(true))
      .catch(() => navigate('/login', { replace: true }));
  }, [navigate]);

  if (!authorized) return null;

  const onPick = (f) => {
    setFile(f);
    setHasil(null);
    setError('');
    if (f) setPreview(URL.createObjectURL(f));
  };

  const buatSeal = async () => {
    if (!file || !pesan.trim()) return;
    setLoading(true);
    setError('');
    setHasil(null);
    const fd = new FormData();
    fd.append('file', file);
    fd.append('pesan', pesan.trim());
    try {
      const res = await upload('/generate', fd);
      setHasil(res);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const download = () => {
    if (!hasil) return;
    const blob = b64ToBlob(hasil.bmp_base64);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'seal_e_receipt.bmp';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  };

  const st = hasil?.stats || {};

  return (
    <div className="container">
      <section className="hero">
        <h1>Generator <span className="grad">Seal E-Receipt</span></h1>
        <p>
          Halaman khusus <strong>admin ({user})</strong>. Upload e-receipt, tulis
          pesan keaslian, lalu sistem menyisipkan pesan terenkripsi ke dalam citra
          dan menghasilkan file <strong>.bmp</strong> tersegel.
        </p>
      </section>

      <div className="two-col">
        {/* FORM */}
        <section className="glass lift">
          <h2 className="card-title"><IconPen size={17} /> Masukkan data</h2>

          <div
            className={`dropzone ${file ? 'has-file' : ''}`}
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); onPick(e.dataTransfer.files?.[0] || null); }}
          >
            <input
              ref={inputRef}
              type="file"
              accept="image/*"
              hidden
              onChange={(e) => onPick(e.target.files?.[0] || null)}
            />
            {preview ? (
              <div className="dz-preview">
                <img src={preview} alt="Pratinjau" />
                <p className="dz-name">{file.name}</p>
              </div>
            ) : (
              <>
                <div className="dz-icon"><IconImage size={26} /></div>
                <p className="dz-title">Upload e-receipt (format apa saja)</p>
                <p className="dz-sub">Otomatis dikonversi ke BMP (lossless) sebelum diproses</p>
              </>
            )}
          </div>

          <label className="field">
            <span>Pesan keaslian (maks {MAX_BYTE} byte)</span>
            <textarea
              value={pesan}
              onChange={(e) => setPesan(potongByte(e.target.value, MAX_BYTE))}
              rows={3}
              placeholder="Contoh: E-RECEIPT ALFAMART #INV-2026-0817 | SAH | DITERBITKAN OLEH SERVER RESMI"
            />
            <small className="counter">{byteLength(pesan)}/{MAX_BYTE} byte</small>
          </label>

          {error && (
            <p className="alert alert-danger">
              <IconX size={15} /> {error}
            </p>
          )}

          <button
            className="btn btn-primary btn-big"
            disabled={!file || !pesan.trim() || loading}
            onClick={buatSeal}
          >
            {loading ? 'Menyisipkan pesan…' : (<><IconShield size={17} /> Buat Seal</>)}
          </button>
        </section>

        {/* HASIL */}
        <section className="glass lift">
          <h2 className="card-title"><IconFile size={17} /> Hasil seal</h2>

          {hasil ? (
            <>
              <div className="seal-preview">
                <img
                  src={`data:image/bmp;base64,${hasil.bmp_base64}`}
                  alt="Seal BMP"
                />
              </div>
              <div className="detail-grid">
                <div className="detail-item">
                  <span className="detail-num">{st.total_salinan ?? '-'}</span>
                  <span className="detail-label">Total salinan</span>
                </div>
                <div className="detail-item">
                  <span className="detail-num">{st.nbytes_per_salinan ?? '-'} B</span>
                  <span className="detail-label">Data per salinan</span>
                </div>
                <div className="detail-item">
                  <span className="detail-num">{st.ukuran ?? '-'}</span>
                  <span className="detail-label">Ukuran citra</span>
                </div>
                <div className="detail-item">
                  <span className="detail-num">{st.waktu ?? '-'} s</span>
                  <span className="detail-label">Waktu proses</span>
                </div>
              </div>
              <button className="btn btn-success btn-big" onClick={download}>
                <IconDownload size={17} /> Download seal_e_receipt.bmp
              </button>
              <p className="hint">
                Verifikasi hasilnya di halaman <strong>Ekstraksi</strong> untuk memastikan status <strong>ABSAH</strong>.
              </p>
            </>
          ) : (
            <div className="placeholder">
              <IconShield size={34} />
              <p>Hasil seal akan tampil di sini setelah proses selesai.</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
