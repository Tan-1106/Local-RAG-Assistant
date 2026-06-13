import { useEffect, useState } from 'react';
import { useAuth } from '../context/auth';
import { API_BASE_URL } from '../config';
import { Scale, MessageSquare, Plus, LogOut, Database, Trash2, X, LogOutIcon } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import ConfirmDialog from './ConfirmDialog';
import { parseSessions } from '../utils/validation';

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
}

interface SidebarProps {
  currentSessionId: string | null;
  onSelectSession: (id: string | null) => void;
  isOpen: boolean;
  onClose: () => void;
  refreshKey: number;
}

export default function Sidebar({
  currentSessionId,
  onSelectSession,
  isOpen,
  onClose,
  refreshKey,
}: SidebarProps) {
  const { user, logout, logoutAll, apiFetch } = useAuth();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [error, setError] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<ChatSession | null>(null);
  const [confirmLogoutAll, setConfirmLogoutAll] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const controller = new AbortController();

    void apiFetch(`${API_BASE_URL}/sessions/`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error(`Không thể tải danh sách phiên (${response.status})`);
        return response.json();
      })
      .then(data => {
        setSessions(parseSessions(data));
        setError('');
      })
      .catch(fetchError => {
        if (!controller.signal.aborted) {
          console.error(fetchError);
          setError('Không thể tải danh sách cuộc trò chuyện.');
        }
      });

    return () => controller.abort();
  }, [apiFetch, currentSessionId, refreshKey]);

  const handleCreateSession = async () => {
    setIsCreating(true);
    setError('');
    try {
      const res = await apiFetch(`${API_BASE_URL}/sessions/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: 'Cuộc trò chuyện mới' }),
      });
      if (!res.ok) throw new Error(`Không thể tạo phiên (${res.status})`);

      const [newSession] = parseSessions([await res.json()]);
      setSessions(previous => [newSession, ...previous]);
      onSelectSession(newSession.id);
    } catch (createError) {
      console.error(createError);
      setError('Không thể tạo cuộc trò chuyện mới.');
    } finally {
      setIsCreating(false);
    }
  };

  const handleDeleteSession = async (id: string) => {
    setDeletingSessionId(id);
    setError('');
    try {
      const response = await apiFetch(`${API_BASE_URL}/sessions/${id}`, { method: 'DELETE' });
      if (!response.ok) throw new Error(`Không thể xóa phiên (${response.status})`);
      setSessions(previous => previous.filter(session => session.id !== id));
      if (currentSessionId === id) onSelectSession(null);
    } catch (deleteError) {
      console.error(deleteError);
      setError('Không thể xóa cuộc trò chuyện.');
    } finally {
      setDeletingSessionId(null);
    }
  };

  const handleLogoutAll = async () => {
    setConfirmLogoutAll(false);
    setError('');
    try {
      await logoutAll();
    } catch (logoutError) {
      console.error(logoutError);
      setError('Không thể đăng xuất khỏi tất cả thiết bị.');
    }
  };

  const handleLogout = async () => {
    setError('');
    try {
      await logout();
    } catch (logoutError) {
      console.error(logoutError);
      setError('Không thể đăng xuất. Vui lòng thử lại.');
    }
  };

  const userInitial = user?.username?.charAt(0).toUpperCase() ?? '?';

  return (
    <aside className={`sidebar ${isOpen ? 'sidebar-open' : ''}`}>
      {/* Mobile close */}
      <button
        type="button"
        className="sidebar-close"
        onClick={onClose}
        aria-label="Đóng menu"
      >
        <X size={16} />
      </button>

      {/* Header / Brand */}
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <Scale size={18} color="#fff" strokeWidth={1.8} />
        </div>
        <div>
          <div className="sidebar-brand">Trợ Lý Pháp Lý</div>
          <div className="sidebar-brand-sub">AI Tư Vấn Pháp Luật</div>
        </div>
      </div>

      {/* Body */}
      <div className="sidebar-body">
        <button
          onClick={handleCreateSession}
          className="sidebar-new-btn"
          disabled={isCreating}
          id="sidebar-new-chat-btn"
        >
          <Plus size={16} />
          <span>{isCreating ? 'Đang tạo...' : 'Cuộc trò chuyện mới'}</span>
        </button>

        {error && (
          <p className="text-xs text-danger px-2" role="alert" aria-live="assertive">{error}</p>
        )}

        {sessions.length > 0 && (
          <p className="sessions-label">Lịch sử</p>
        )}

        {sessions.map(s => (
          <div
            key={s.id}
            onClick={() => onSelectSession(s.id)}
            onKeyDown={event => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                onSelectSession(s.id);
              }
            }}
            role="button"
            tabIndex={0}
            className={`session-item ${currentSessionId === s.id ? 'active' : ''}`}
            id={`session-item-${s.id}`}
          >
            <MessageSquare size={14} className="text-faint shrink-0" />
            <span className="session-title">{s.title}</span>
            <button
              type="button"
              onClick={event => {
                event.stopPropagation();
                setPendingDelete(s);
              }}
              className="session-delete-btn"
              disabled={deletingSessionId === s.id}
              aria-label={`Xóa ${s.title}`}
            >
              <Trash2 size={13} />
            </button>
          </div>
        ))}

        {sessions.length === 0 && !error && (
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <MessageSquare size={24} className="text-faint" />
            <p className="text-xs text-faint">Chưa có cuộc trò chuyện nào</p>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="sidebar-footer">
        {user?.role === 'admin' && (
          <button
            onClick={() => { navigate('/admin/documents'); onClose(); }}
            className="btn btn-secondary w-full justify-start text-sm"
            id="sidebar-admin-btn"
          >
            <Database size={15} />
            <span>Quản lý Tài liệu</span>
          </button>
        )}

        <div className="user-card">
          <div className="user-avatar">{userInitial}</div>
          <div className="user-info">
            <div className="user-name">{user?.username}</div>
            <div className="user-role">{user?.role}</div>
          </div>
          <button
            type="button"
            onClick={handleLogout}
            className="btn btn-ghost icon-button"
            title="Đăng xuất"
            id="sidebar-logout-btn"
          >
            <LogOut size={15} />
          </button>
        </div>

        <button
          type="button"
          className="btn btn-ghost w-full text-xs text-faint"
          onClick={() => setConfirmLogoutAll(true)}
          id="sidebar-logout-all-btn"
        >
          <LogOutIcon size={12} />
          Đăng xuất tất cả thiết bị
        </button>
      </div>

      {pendingDelete && (
        <ConfirmDialog
          title="Xóa cuộc trò chuyện?"
          message={`"${pendingDelete.title}" sẽ bị xóa vĩnh viễn.`}
          confirmLabel="Xóa"
          onCancel={() => setPendingDelete(null)}
          onConfirm={() => {
            const id = pendingDelete.id;
            setPendingDelete(null);
            void handleDeleteSession(id);
          }}
        />
      )}
      {confirmLogoutAll && (
        <ConfirmDialog
          title="Đăng xuất tất cả thiết bị?"
          message="Mọi phiên đăng nhập hiện tại của tài khoản sẽ bị thu hồi."
          confirmLabel="Đăng xuất tất cả"
          onCancel={() => setConfirmLogoutAll(false)}
          onConfirm={() => void handleLogoutAll()}
        />
      )}
    </aside>
  );
}
