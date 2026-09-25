import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { authApi } from '../api';
import { useAuth } from '../App';
import { IconLock, IconX } from '../components/Icons.jsx';

export default function Login() {
  const { setUser } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const res = await authApi.login(username.trim(), password);
      setUser(res.username);
      navigate('/generator');
    } catch (err) {
      setError(err.message || 'Login gagal');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container narrow">
      <section className="glass login-card">
        <div className="login-icon"><IconLock size={26} /></div>
        <h1>Login Admin</h1>
        <p className="login-sub">
          Halaman <strong>Generator</strong> hanya untuk admin (pemilik/atasan)
          yang berhak menanam pesan ke e-receipt.
        </p>
        <form onSubmit={submit}>
          <label className="field">
            <span>Username</span>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="admin"
              autoComplete="username"
              required
            />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
              required
            />
          </label>
          {error && (
            <p className="alert alert-danger">
              <IconX size={15} /> {error}
            </p>
          )}
          <button className="btn btn-primary btn-big" disabled={loading}>
            {loading ? 'Memproses…' : 'Masuk'}
          </button>
        </form>
      </section>
    </div>
  );
}
