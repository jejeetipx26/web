import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { NavLink, Route, Routes, useNavigate, Link } from 'react-router-dom';
import { authApi } from './api';
import Ekstraksi from './pages/Ekstraksi.jsx';
import Login from './pages/Login.jsx';
import Generator from './pages/Generator.jsx';
import { IconShield, IconScan, IconPen, IconUser, IconLogout } from './components/Icons.jsx';

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const onLogout = async () => {
    await authApi.logout().catch(() => {});
    logout();
    navigate('/');
  };

  return (
    <header className="navbar">
      <div className="navbar-inner">
        <Link to="/" className="brand">
          <span className="brand-logo"><IconShield size={21} /></span>
          <span>
            <strong>E-Receipt Guard</strong>
            <small>Deteksi Keabsahan E-Receipt</small>
          </span>
        </Link>
        <nav className="nav-links">
          <NavLink to="/" end className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
            <IconScan size={17} /> Ekstraksi
          </NavLink>
          {user && (
            <NavLink to="/generator" className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
              <IconPen size={17} /> Generator
            </NavLink>
          )}
        </nav>
        <div className="nav-user">
          {user ? (
            <>
              <span className="user-chip"><IconUser size={15} /> {user}</span>
              <button className="btn btn-ghost" onClick={onLogout}>
                <IconLogout size={15} /> Keluar
              </button>
            </>
          ) : (
            <Link to="/login" className="btn btn-primary">Login Admin</Link>
          )}
        </div>
      </div>
    </header>
  );
}

export default function App() {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    authApi.me()
      .then((d) => setUser(d.username))
      .catch(() => setUser(null))
      .finally(() => setChecking(false));
  }, []);

  const logout = useCallback(() => setUser(null), []);

  if (checking) {
    return (
      <div className="loading-screen">
        <IconShield size={44} />
        <p>Memuat sistem…</p>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={{ user, setUser, logout }}>
      <Navbar />
      <main className="page">
        <Routes>
          <Route path="/" element={<Ekstraksi />} />
          <Route path="/login" element={<Login />} />
          <Route path="/generator" element={<Generator />} />
        </Routes>
      </main>
      <footer className="footer">
        <p className="footer-main">
          Sistem Deteksi Keabsahan E-Receipt — Steganografi LSB 2-bit · AES-GCM · Majority Voting
        </p>
        <p className="footer-copy">© 2026 <span>JejeeTipx26@Skripsi</span></p>
      </footer>
    </AuthContext.Provider>
  );
}
