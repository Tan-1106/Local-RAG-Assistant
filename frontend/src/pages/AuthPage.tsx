import React, { useState, useEffect } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth, type User } from '../context/auth';
import { API_BASE_URL } from '../config';
import { Scale, Eye, EyeOff } from 'lucide-react';
import { fetchWithTimeout } from '../utils/api';
import { parseUser } from '../utils/validation';

export default function AuthPage() {
  const [isLogin, setIsLogin] = useState(true);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
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
    setIsSubmitting(true);

    try {
      if (isLogin) {
        // Login uses form-data
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
        if (!csrfToken) {
          throw new Error('Phản hồi đăng nhập thiếu CSRF token');
        }
        login(userData, csrfToken);
      } else {
        // Register uses JSON
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
        setError('Đăng ký thành công! Hãy đăng nhập.');
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Có lỗi xảy ra');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="app-container items-center justify-center" style={{ backgroundImage: 'radial-gradient(circle at 50% 50%, #2a2a35 0%, #1a1a20 100%)' }}>
      <div className="glass-panel p-4" style={{ width: '400px', maxWidth: '90%' }}>
        <div className="flex flex-col items-center mb-4 mt-2">
          <div className="p-2 glass rounded-full mb-2">
            <Scale size={32} color="hsl(var(--primary))" />
          </div>
          <h2 className="text-xl font-bold">{isLogin ? 'Đăng Nhập Hệ Thống' : 'Đăng Ký Tài Khoản'}</h2>
          <p className="text-sm text-muted">Hệ thống AI tra cứu luật pháp</p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className="text-sm font-medium mb-2 block">Tài khoản</label>
            <input 
              className="input" 
              type="text" 
              required 
              minLength={3}
              maxLength={50}
              autoComplete="username"
              value={username} 
              onChange={e => setUsername(e.target.value)} 
              placeholder="Nhập tên đăng nhập"
            />
          </div>
          
          <div>
            <label className="text-sm font-medium mb-2 block">Mật khẩu</label>
            <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
              <input 
                className="input" 
                type={showPassword ? "text" : "password"} 
                required 
                minLength={isLogin ? undefined : 6}
                maxLength={128}
                autoComplete={isLogin ? 'current-password' : 'new-password'}
                value={password} 
                onChange={e => setPassword(e.target.value)} 
                placeholder="••••••••"
                style={{ paddingRight: '2.5rem' }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="btn btn-ghost"
                aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
                style={{
                  position: 'absolute',
                  right: '4px',
                  height: 'calc(2.5rem - 8px)',
                  padding: '0 8px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: 'transparent',
                  border: 'none',
                }}
              >
                {showPassword ? (
                  <EyeOff size={16} className="text-muted" />
                ) : (
                  <Eye size={16} className="text-muted" />
                )}
              </button>
            </div>
          </div>

          {error && (
            <p
              className="text-sm"
              role="status"
              aria-live="polite"
              style={{ color: error.includes('thành công') ? 'green' : 'hsl(var(--destructive))' }}
            >
              {error}
            </p>
          )}

          <button type="submit" className="btn btn-primary w-full mt-2" disabled={isSubmitting}>
            {isSubmitting ? 'Đang xử lý...' : isLogin ? 'Đăng Nhập' : 'Đăng Ký'}
          </button>
        </form>

        <div className="mt-4 flex justify-center">
          <button 
            type="button" 
            className="btn btn-ghost text-sm text-muted"
            disabled={isSubmitting}
            onClick={() => { setIsLogin(!isLogin); setError(''); setShowPassword(false); }}
          >
            {isLogin ? 'Chưa có tài khoản? Đăng ký ngay' : 'Đã có tài khoản? Đăng nhập'}
          </button>
        </div>
      </div>
    </div>
  );
}
