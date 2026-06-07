import { useEffect, useState } from 'react';
import { useAuth } from '../context/auth';
import { API_BASE_URL } from '../config';
import { MessageSquare, Plus, LogOut, Database, Trash2 } from 'lucide-react';
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
        if (!response.ok) {
          throw new Error(`Không thể tải danh sách phiên (${response.status})`);
        }
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
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ title: "Cuộc trò chuyện mới" })
      });
      if (!res.ok) {
        throw new Error(`Không thể tạo phiên (${res.status})`);
      }

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
      const response = await apiFetch(`${API_BASE_URL}/sessions/${id}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        throw new Error(`Không thể xóa phiên (${response.status})`);
      }

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

  return (
    <aside className={`sidebar p-4 justify-between ${isOpen ? 'sidebar-open' : ''}`}>
      <button type="button" className="sidebar-close btn btn-ghost" onClick={onClose} aria-label="Đóng menu">
        ×
      </button>
      <div className="flex-col gap-4 h-full" style={{ overflowY: 'auto' }}>
        <button 
          onClick={handleCreateSession}
          className="btn btn-primary w-full justify-between mb-4"
          disabled={isCreating}
        >
          <span>{isCreating ? 'Đang tạo...' : 'Chat mới'}</span>
          <Plus size={18} />
        </button>

        <div className="flex-col gap-2">
          <p className="text-xs text-muted font-bold px-2 mb-2">LỊCH SỬ</p>
          {error && <p className="text-xs text-danger px-2 mb-2" role="alert" aria-live="assertive">{error}</p>}
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
              className={`flex items-center justify-between p-2 rounded cursor-pointer ${currentSessionId === s.id ? 'glass' : 'btn-ghost'}`}
            >
              <div className="flex items-center gap-2 truncate">
                <MessageSquare size={16} className="text-muted" />
                <span className="text-sm truncate">{s.title}</span>
              </div>
              <button
                onClick={(event) => {
                  event.stopPropagation();
                  setPendingDelete(s);
                }}
                className="btn-ghost p-1 rounded"
                disabled={deletingSessionId === s.id}
                aria-label={`Xóa ${s.title}`}
              >
                <Trash2 size={14} className="text-muted hover:text-destructive" />
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="flex-col gap-2 mt-4 pt-4" style={{ borderTop: '1px solid hsl(var(--border))' }}>
        {user?.role === 'admin' && (
          <button 
            onClick={() => {
              navigate('/admin/documents');
              onClose();
            }}
            className="btn btn-secondary w-full justify-start gap-2"
          >
            <Database size={16} />
            <span className="text-sm">Quản lý Tài liệu</span>
          </button>
        )}
        
        <div className="flex items-center justify-between mt-2 px-2">
          <div className="flex-col">
            <span className="text-sm font-bold truncate">{user?.username}</span>
            <span className="text-xs text-muted uppercase">{user?.role}</span>
          </div>
          <button onClick={handleLogout} className="btn-ghost p-2 rounded-full" title="Đăng xuất">
            <LogOut size={16} />
          </button>
        </div>
        <button
          type="button"
          className="btn btn-ghost w-full text-xs"
          onClick={() => setConfirmLogoutAll(true)}
        >
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
