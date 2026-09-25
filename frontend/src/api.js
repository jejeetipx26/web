// Klien API sederhana — semua panggilan memakai cookie sesi (HttpOnly).
const API = '/api';

async function handle(res) {
  if (!res.ok) {
    let msg = 'Terjadi kesalahan pada server';
    try {
      const j = await res.json();
      if (j.detail) msg = j.detail;
    } catch { /* abaikan */ }
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export function api(path, options = {}) {
  return fetch(API + path, { credentials: 'include', ...options }).then(handle);
}

export function upload(path, formData) {
  return fetch(API + path, {
    method: 'POST',
    credentials: 'include',
    body: formData,
  }).then(handle);
}

export const authApi = {
  me: () => api('/auth/me'),
  login: (username, password) =>
    api('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    }),
  logout: () => api('/auth/logout', { method: 'POST' }),
};

// ---- util ----
export function b64ToBlob(b64, mime = 'image/bmp') {
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return new Blob([arr], { type: mime });
}
