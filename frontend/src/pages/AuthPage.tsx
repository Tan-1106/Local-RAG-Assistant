import React, { useState, useEffect } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth, type User } from '../context/auth';
import { API_BASE_URL } from '../config';
import { Scale, Eye, EyeOff, ArrowRight, Loader2 } from 'lucide-react';
import { fetchWithTimeout } from '../utils/api';
import { parseUser } from '../utils/validation';

export default function AuthPage() {
  const [isLogin, setIsLogin] = useState(true);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isSuccess, setIsSuccess] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { user, login } = useAuth();

  useEffect(() => {
    document.title = isLogin ? 'Đăng Nhập - Trợ Lý Pháp Lý' : 'Đăng Ký - Trợ Lý Pháp Lý';
  }, [isLogin]);

  if (user) {
    return <Navigate to="/" replace />;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsSuccess(false);
    setIsSubmitting(true);

    try {
      if (isLogin) {
        const formData = new URLSearchParams();
        formData.append('username', username);
        formData.append('password', password);

        const res = await fetchWithTimeout(`${API_BASE_URL}/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: formData.toString(),
          credentials: 'include',
        });

        if (res.status === 429) {
          const retryAfter = res.headers.get('Retry-After');
          throw new Error(`Thử đăng nhập lại sau ${retryAfter ?? 'một lúc'} giây.`);
        }
        if (!res.ok) throw new Error('Sai tài khoản hoặc mật khẩu');
        const userData: User = parseUser(await res.json());
        const csrfToken = res.headers.get('X-CSRF-Token');
        if (!csrfToken) throw new Error('Phản hồi đăng nhập thiếu CSRF token');
        login(userData, csrfToken);
      } else {
        const res = await fetchWithTimeout(`${API_BASE_URL}/auth/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password }),
          credentials: 'include',
        });

        if (res.status === 429) {
          const retryAfter = res.headers.get('Retry-After');
          throw new Error(`Thử đăng ký lại sau ${retryAfter ?? 'một lúc'} giây.`);
        }
        if (!res.ok) throw new Error('Tài khoản đã tồn tại hoặc có lỗi xảy ra');

        setIsLogin(true);
        setIsSuccess(true);
        setError('Đăng ký thành công! Hãy đăng nhập.');
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Có lỗi xảy ra');
      setIsSuccess(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="glass-panel auth-card animate-slide-up">
        {/* Logo */}
        <div className="auth-logo-wrap">
          <div className="auth-logo">
            <Scale size={28} color="#fff" strokeWidth={1.5} />
          </div>
          <div>
            <h1 className="auth-title">
              {isLogin ? 'Đăng nhập hệ thống' : 'Tạo tài khoản'}
            </h1>
            <p className="auth-subtitle">Nền tảng AI tư vấn pháp luật Việt Nam</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="auth-form" id="auth-form">
          <div className="auth-field">
            <label htmlFor="auth-username" className="input-label">Tài khoản</label>
            <input
              id="auth-username"
              className="input"
              type="text"
              required
              minLength={3}
              maxLength={50}
              autoComplete="username"
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="Nhập tên đăng nhập"
              disabled={isSubmitting}
            />
          </div>

          <div className="auth-field">
            <label htmlFor="auth-password" className="input-label">Mật khẩu</label>
            <div className="auth-password-wrap">
              <input
                id="auth-password"
                className="input"
                type={showPassword ? 'text' : 'password'}
                required
                minLength={isLogin ? undefined : 6}
                maxLength={128}
                autoComplete={isLogin ? 'current-password' : 'new-password'}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                disabled={isSubmitting}
              />
              <button
                type="button"
                className="auth-eye-btn"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
              >
                {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>

          {error && (
            <div
              className={`auth-error ${isSuccess ? 'success' : 'error'}`}
              role="status"
              aria-live="polite"
            >
              {error}
            </div>
          )}

          <button
            type="submit"
            className="auth-submit-btn"
            disabled={isSubmitting}
            id="auth-submit-btn"
          >
            {isSubmitting ? (
              <><Loader2 size={16} className="spin" /> Đang xử lý...</>
            ) : (
              <>{isLogin ? 'Đăng nhập' : 'Tạo tài khoản'} <ArrowRight size={16} /></>
            )}
          </button>
        </form>

        <div className="auth-switch">
          <button
            type="button"
            className="auth-switch-btn"
            disabled={isSubmitting}
            onClick={() => { setIsLogin(!isLogin); setError(''); setIsSuccess(false); setShowPassword(false); }}
          >
            {isLogin ? 'Chưa có tài khoản? Đăng ký ngay →' : 'Đã có tài khoản? Đăng nhập →'}
          </button>
        </div>
      </div>
    </div>
  );
}
