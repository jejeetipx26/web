import { useEffect, useRef, useState } from 'react';
import { upload } from '../api';
import { IconCheckCircle, IconXCircle, IconAlert, IconBan, IconSearch, IconMessage, IconFile, IconX, IconLayers, IconRuler, IconLock } from '../components/Icons.jsx';

const STATUS_STYLE = {
  'ABSAH': { Icon: IconCheckCircle, cls: 'badge badge-ok', tip: 'Seal sah — belum pernah diubah.' },
  'TIDAK ABSAH': { Icon: IconXCircle, cls: 'badge badge-danger', tip: 'Ada bagian citra yang diubah/dipalsukan.' },
  'TIDAK TERVERIFIKASI': { Icon: IconAlert, cls: 'badge badge-warn', tip: 'Tidak ada salinan yang bisa didekripsi (kunci salah / rusak parah).' },
  'DITOLAK (bukan BMP)': { Icon: IconBan, cls: 'badge badge-danger', tip: 'Sistem hanya menerima file BMP (lossless). JPG/PNG ditolak.' },
};

function PetaKerusakan({ preview, blocks }) {
  const canvasRef = useRef(null);
  const miniRef = useRef(null);
  const [info, setInfo] = useState(null);

  useEffect(() => {
    if (!preview) return;
    const img = new Image();
    img.onload = () => {
      const W = img.naturalWidth, H = img.naturalHeight;
      const blk = blocks || [];

      // ===== CANVAS UTAMA: citra + garis grid + overlay merah =====
      const canvas = canvasRef.current;
      if (canvas) {
        canvas.width = W;
        canvas.height = H;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0);

        // garis grid 16×16 px (biar terlihat sel mana saja)
        ctx.strokeStyle = 'rgba(15, 59, 89, 0.18)';
        ctx.lineWidth = 1;
        for (let gx = 0; gx <= W; gx += 16) {
          ctx.beginPath(); ctx.moveTo(gx + 0.5, 0); ctx.lineTo(gx + 0.5, H); ctx.stroke();
        }
        for (let gy = 0; gy <= H; gy += 16) {
          ctx.beginPath(); ctx.moveTo(0, gy + 0.5); ctx.lineTo(W, gy + 0.5); ctx.stroke();
        }

        // overlay merah semi-transparan pada blok yang dimodifikasi
        ctx.fillStyle = 'rgba(220, 38, 38, 0.45)';
        ctx.strokeStyle = '#dc2626';
        ctx.lineWidth = 1.5;
        for (const b of blk) {
          ctx.fillRect(b.x, b.y, b.ukuran, b.ukuran);
          ctx.strokeRect(b.x + 0.5, b.y + 0.5, b.ukuran - 1, b.ukuran - 1);
        }
      }

      // ===== MINI-MAP: peta skematik grid (1 sel grid = 4px) =====
      const mini = miniRef.current;
      if (mini) {
        const cell = 4; // ukuran tiap sel grid di peta (px)
        mini.width = Math.ceil(W / 16) * cell;
        mini.height = Math.ceil(H / 16) * cell;
        const mctx = mini.getContext('2d');
        mctx.fillStyle = 'rgba(15, 59, 89, 0.10)';
        mctx.fillRect(0, 0, mini.width, mini.height);
        mctx.fillStyle = '#dc2626';
        for (const b of blk) {
          const k = b.ukuran / 16; // berapa sel grid yang dicakup blok
          mctx.fillRect((b.x / 16) * cell, (b.y / 16) * cell, k * cell, k * cell);
        }
      }

      // ===== RINGKASAN AREA =====
      if (blk.length) {
        let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
        for (const b of blk) {
          x0 = Math.min(x0, b.x); y0 = Math.min(y0, b.y);
          x1 = Math.max(x1, b.x + b.ukuran); y1 = Math.max(y1, b.y + b.ukuran);
        }
        setInfo({
          x0, y0, x1, y1, n: blk.length, W, H,
          gx0: Math.floor(x0 / 16), gy0: Math.floor(y0 / 16),
          gx1: Math.floor((x1 - 1) / 16), gy1: Math.floor((y1 - 1) / 16),
        });
      } else {
        setInfo(null);
      }
    };
    img.src = preview;
  }, [preview, blocks]);

  const posisi = info ? (() => {
    const cx = (info.x0 + info.x1) / 2 / info.W;
    const cy = (info.y0 + info.y1) / 2 / info.H;
    const x = cx < 0.33 ? 'kiri' : cx > 0.66 ? 'kanan' : 'tengah';
    const y = cy < 0.33 ? 'atas' : cy > 0.66 ? 'bawah' : 'tengah';
    if (x === 'tengah' && y === 'tengah') return 'bagian tengah dokumen';
    if (x === 'tengah') return `bagian ${y} dokumen`;
    return `bagian ${y}-${x} dokumen`;
  })() : '';

  const isiBagian = info ? (() => {
    const cy = (info.y0 + info.y1) / 2 / info.H;
    if (cy < 0.15) return 'header dokumen (nama toko / logo)';
    if (cy < 0.35) return 'info transaksi (tanggal, nomor, kasir)';
    if (cy < 0.70) return 'daftar item belanja';
    if (cy < 0.85) return 'area total belanja / nominal';
    return 'area pembayaran / kembalian / footer';
  })() : '';

  return (
    <div className="tamper-box">
      <div className="pesan-label"><IconRuler size={13} /> Lokasi Bagian yang Dimodifikasi</div>

      <div className="tamper-main">
        <div className="tamper-canvas-wrap">
          <canvas ref={canvasRef} className="tamper-canvas" />
          <span className="tamper-cap">Kotak <strong>merah</strong> = blok grid yang diubah</span>
        </div>
        <div className="tamper-mini-wrap">
          <span className="tamper-mini-label">Peta grid (sel yang diubah)</span>
          <canvas ref={miniRef} className="tamper-mini" />
        </div>
      </div>

      {info && (
        <ul className="tamper-list">
          <li><strong>{info.n} blok</strong> terdeteksi termodifikasi.</li>
          <li>Grid yang diubah: <strong>kolom {info.gx0}–{info.gx1}</strong>, <strong>baris {info.gy0}–{info.gy1}</strong> (sel grid 16×16 px).</li>
          <li>Berada di {posisi} — kemungkinan berisi <strong>{isiBagian}</strong>.</li>
          <li>Area modifikasi: kolom {info.x0}–{info.x1}, baris {info.y0}–{info.y1} (piksel).</li>
        </ul>
      )}
    </div>
  );
}

export default function Ekstraksi() {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [hasil, setHasil] = useState(null);
  const [error, setError] = useState('');

  const onPick = (f) => {
    setFile(f);
    setHasil(null);
    setError('');
    if (f) setPreview(URL.createObjectURL(f));
  };

  const periksa = async () => {
    if (!file) return;
    setLoading(true);
    setError('');
    setHasil(null);
    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await upload('/verify', fd);
      setHasil(res);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const s = hasil ? (STATUS_STYLE[hasil.status] || STATUS_STYLE['TIDAK TERVERIFIKASI']) : null;

  return (
    <div className="container">
      {/* HERO */}
      <section className="hero">
        <h1>Periksa Keabsahan <span className="grad">E-Receipt</span></h1>
        <p>
          Upload file <strong>.bmp</strong> e-receipt untuk memeriksa apakah masih
          asli dan sah. Sistem mengekstrak pesan tersembunyi dari ribuan salinan
          (4 blok sudut + blok grid) lalu melakukan <em>majority voting</em>.
        </p>
        <div className="hero-badges">
          <span><IconLock size={13} /> AES-GCM</span>
          <span><IconRuler size={13} /> LSB 2-bit</span>
          <span><IconLayers size={13} /> Majority Voting</span>
        </div>
      </section>

      {/* UPLOAD CARD */}
      <section className="glass upload-card lift">
        <div
          className={`dropzone ${file ? 'has-file' : ''}`}
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); onPick(e.dataTransfer.files?.[0] || null); }}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".bmp,image/bmp"
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
              <div className="dz-icon"><IconFile size={26} /></div>
              <p className="dz-title">Klik atau tarik file BMP ke sini</p>
              <p className="dz-sub">Hanya file <strong>.bmp</strong> yang dapat diproses — format lain ditolak</p>
            </>
          )}
        </div>

        <button className="btn btn-primary btn-big" disabled={!file || loading} onClick={periksa}>
          {loading ? 'Memeriksa…' : (<><IconSearch size={17} /> Periksa Keabsahan</>)}
        </button>
        {file && !hasil && !error && (
          <p className="hint">File: <strong>{file.name}</strong> ({Math.round(file.size / 1024)} KB)</p>
        )}
        {error && (
          <p className="alert alert-danger">
            <IconX size={16} /> {error}
          </p>
        )}
      </section>

      {/* HASIL */}
      {hasil && s && (
        <section className="glass result-card">
          <div className="result-head">
            <span className={s.cls}><s.Icon size={19} /> {hasil.status}</span>
            <p className="result-tip">{s.tip}</p>
          </div>

          {hasil.status === 'ABSAH' && hasil.detail?.pesan && (
            <div className="pesan-box">
              <div className="pesan-label"><IconMessage size={13} /> Pesan terbaca dari seal</div>
              <div className="pesan-text">{hasil.detail.pesan}</div>
            </div>
          )}

          {hasil.status === 'TIDAK ABSAH' && (
            <PetaKerusakan preview={preview} blocks={hasil.detail?.peta_rusak || []} />
          )}

          <div className="detail-grid">
            <div className="detail-item">
              <span className="detail-num">{hasil.detail?.total_salinan ?? 0}</span>
              <span className="detail-label">Total salinan</span>
            </div>
            <div className="detail-item">
              <span className="detail-num ok">{hasil.detail?.salinan_ok ?? 0}</span>
              <span className="detail-label">Salinan identik</span>
            </div>
            <div className="detail-item">
              <span className="detail-num bad">{hasil.detail?.blok_rusak ?? 0}</span>
              <span className="detail-label">Blok rusak</span>
            </div>
            <div className="detail-item">
              <span className="detail-num">{hasil.detail?.waktu ?? '-'} s</span>
              <span className="detail-label">Waktu proses</span>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
