import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, CheckCircle, Loader2, UploadCloud, XCircle, Database,
  Trash2, AlertTriangle, FileText, RefreshCw, Eye, EyeOff,
} from 'lucide-react';
import {
  API_BASE_URL,
  UPLOAD_MAX_FILE_BYTES,
  UPLOAD_MAX_FILES,
  UPLOAD_MAX_TOTAL_BYTES,
  UPLOAD_TIMEOUT_MS,
} from '../config';
import { useAuth } from '../context/auth';
import { useTranslation } from 'react-i18next';

// ── Types ──
interface Task {
  task_id: string;
  type: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  meta: { files?: string[]; count?: number };
  error?: string;
  updated_at: number;
}

interface DocumentInfo {
  filename: string;
  size_bytes: number;
}

// ── Constants ──
const TASK_STORAGE_PREFIX = 'legal-assistant-admin-tasks';
const TASK_RETENTION_MS = 24 * 60 * 60 * 1000;
const ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.txt'];

function storageKey(username: string) { return `${TASK_STORAGE_PREFIX}:${username}`; }

function parseTask(value: unknown): Task | null {
  if (!value || typeof value !== 'object') return null;
  const candidate = value as Partial<Task>;
  if (
    typeof candidate.task_id !== 'string'
    || typeof candidate.type !== 'string'
    || !['queued', 'processing', 'completed', 'failed'].includes(candidate.status ?? '')
    || typeof candidate.updated_at !== 'number'
    || !candidate.meta
    || typeof candidate.meta !== 'object'
  ) return null;
  return candidate as Task;
}

function loadStoredTasks(username: string): Task[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(storageKey(username)) ?? '[]');
    if (!Array.isArray(parsed)) return [];
    const cutoff = Date.now() - TASK_RETENTION_MS;
    return parsed.map(parseTask)
      .filter((task): task is Task => Boolean(task && task.updated_at >= cutoff))
      .slice(0, 50);
  } catch { return []; }
}

function taskFromResponse(value: unknown, current: Task): Task {
  if (!value || typeof value !== 'object') throw new Error('Invalid task response');
  const response = value as Record<string, unknown>;
  const status = response.status;
  if (!['queued', 'processing', 'completed', 'failed'].includes(String(status))) throw new Error('Unknown task status');
  const meta = response.meta && typeof response.meta === 'object' ? response.meta as Task['meta'] : current.meta;
  return {
    ...current,
    status: status as Task['status'],
    meta,
    error: typeof response.error === 'string' && response.error ? response.error : undefined,
    updated_at: Date.now(),
  };
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

// ── Password Modal ──
interface PasswordModalProps {
  title: string;
  description: string;
  onConfirm: (password: string) => Promise<void>;
  onCancel: () => void;
}

function PasswordModal({ title, description, onConfirm, onCancel }: PasswordModalProps) {
  const { t } = useTranslation();
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password.trim()) return;
    setIsLoading(true);
    setError('');
    try {
      await onConfirm(password);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('admin.verification_failed'));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="dialog-backdrop" onClick={e => { if (e.target === e.currentTarget) onCancel(); }}>
      <div className="glass-panel dialog-panel animate-slide-up">
        <div className="flex items-center gap-3">
          <div style={{
            width: 36, height: 36, borderRadius: 8,
            background: 'var(--danger-bg)', border: '1px solid var(--danger-border)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
          }}>
            <AlertTriangle size={18} style={{ color: '#e74c3c' }} />
          </div>
          <div>
            <h3 className="dialog-title">{title}</h3>
          </div>
        </div>

        <p className="dialog-message">{description}</p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <div>
            <label className="input-label" htmlFor="danger-password">{t('admin.enter_admin_password')}</label>
            <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
              <input
                ref={inputRef}
                id="danger-password"
                className="input"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                style={{ paddingRight: '2.75rem' }}
                required
                disabled={isLoading}
              />
              <button
                type="button"
                className="auth-eye-btn"
                onClick={() => setShowPassword(!showPassword)}
                aria-label="Toggle password"
              >
                {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>

          {error && (
            <div className="auth-error error" role="alert">{error}</div>
          )}

          <div className="dialog-actions">
            <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={isLoading}>{t('common.cancel')}</button>
            <button type="submit" className="btn btn-danger" disabled={!password.trim() || isLoading}>
              {isLoading ? <><Loader2 size={14} className="spin" /> {t('auth.processing')}</> : t('admin.confirm_delete')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Main Page ──
export default function AdminDocumentsPage() {
  const { t } = useTranslation();
  const { apiFetch, user } = useAuth();
  const navigate = useNavigate();
  const username = user?.username ?? 'anonymous';
  const [tasks, setTasks] = useState<Task[]>(() => loadStoredTasks(username));
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState('');
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [deletingFile, setDeletingFile] = useState<string | null>(null);
  const [passwordModal, setPasswordModal] = useState<null | 'all-docs' | 'all-sessions'>(null);

  const activeTaskKey = useMemo(
    () => tasks
      .filter(task => task.status === 'queued' || task.status === 'processing')
      .map(task => task.task_id)
      .sort()
      .join('|'),
    [tasks],
  );

  // Persist tasks
  useEffect(() => {
    try { localStorage.setItem(storageKey(username), JSON.stringify(tasks.slice(0, 50))); }
    catch (storageError) { console.error('Could not persist task history', storageError); }
  }, [tasks, username]);

  // Poll active tasks
  useEffect(() => {
    if (!activeTaskKey) return;
    const activeTaskIds = activeTaskKey.split('|');
    const controller = new AbortController();
    let timer: number | undefined;

    const poll = async () => {
      for (const taskId of activeTaskIds) {
        if (controller.signal.aborted) return;
        try {
          const response = await apiFetch(`${API_BASE_URL}/documents/tasks/${encodeURIComponent(taskId)}`, { signal: controller.signal });
          if (response.ok) {
            const data: unknown = await response.json();
            setTasks(previous => previous.map(item => item.task_id === taskId ? taskFromResponse(data, item) : item));
          } else if (response.status === 404) {
            setTasks(previous => previous.map(item =>
              item.task_id === taskId ? { ...item, status: 'failed', error: t('admin.job_expired'), updated_at: Date.now() } : item
            ));
          }
        } catch (pollError) {
          if (!controller.signal.aborted) console.error(pollError);
        }
      }
      if (!controller.signal.aborted) timer = window.setTimeout(poll, 2000);
    };

    void poll();
    return () => { controller.abort(); if (timer) window.clearTimeout(timer); };
  }, [activeTaskKey, apiFetch]);

  // Load documents list
  const loadDocuments = useCallback(async () => {
    try {
      const res = await apiFetch(`${API_BASE_URL}/documents/`);
      if (res.ok) {
        const data = await res.json() as unknown;
        if (Array.isArray(data)) {
          setDocuments(data.map((d: unknown) => {
            const item = d as Record<string, unknown>;
            return { filename: String(item.filename ?? ''), size_bytes: Number(item.size_bytes ?? 0) };
          }));
        }
      }
    } catch { /* silent */ }
  }, [apiFetch]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadDocuments(), 0);
    return () => window.clearTimeout(timer);
  }, [loadDocuments]);

  // Upload handler
  const processUpload = async (selectedFiles: File[]) => {
    const unsupported = selectedFiles.filter(f => !ALLOWED_EXTENSIONS.some(ext => f.name.toLowerCase().endsWith(ext)));
    const oversized = selectedFiles.filter(f => f.size > UPLOAD_MAX_FILE_BYTES);
    const totalBytes = selectedFiles.reduce((sum, f) => sum + f.size, 0);

    if (selectedFiles.length > UPLOAD_MAX_FILES) { setError(t('admin.err_max_files', { count: UPLOAD_MAX_FILES })); return; }
    if (unsupported.length > 0) { setError(t('admin.err_unsupported_files', { files: unsupported.map(f => f.name).join(', ') })); return; }
    if (oversized.length > 0 || totalBytes > UPLOAD_MAX_TOTAL_BYTES) { setError(t('admin.err_file_limits')); return; }

    setIsUploading(true);
    setError('');
    const formData = new FormData();
    selectedFiles.forEach(file => formData.append('files', file));

    try {
      const response = await apiFetch(`${API_BASE_URL}/documents/ingest`, {
        method: 'POST', body: formData, retryOnAuth: false, timeoutMs: UPLOAD_TIMEOUT_MS,
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null) as { detail?: string } | null;
        throw new Error(detail?.detail ?? t('admin.err_status_code', { status: response.status }));
      }
      const data = await response.json() as Record<string, unknown>;
      if (typeof data.task_id !== 'string' || !Array.isArray(data.files)) throw new Error(t('admin.err_invalid_enqueue'));
      const queuedTask: Task = { task_id: data.task_id as string, type: 'ingest', status: 'queued', meta: { files: data.files as string[] }, updated_at: Date.now() };
      setTasks(previous => [queuedTask, ...previous].slice(0, 50));
      void loadDocuments();
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : t('admin.err_cannot_upload'));
    } finally {
      setIsUploading(false);
    }
  };

  const handleFileInputChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const input = event.currentTarget;
    if (!input.files?.length) return;
    await processUpload(Array.from(input.files));
    input.value = '';
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (isUploading) return;
    await processUpload(Array.from(e.dataTransfer.files));
  };

  const handleDeleteFile = async (filename: string) => {
    setDeletingFile(filename);
    try {
      const res = await apiFetch(`${API_BASE_URL}/documents/${encodeURIComponent(filename)}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(t('admin.err_delete_failed', { status: res.status }));
      setDocuments(prev => prev.filter(d => d.filename !== filename));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('admin.err_cannot_delete'));
    } finally {
      setDeletingFile(null);
    }
  };

  const handleDeleteAllDocs = async (password: string) => {
    const res = await apiFetch(`${API_BASE_URL}/documents/all`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({})) as { detail?: string };
      throw new Error(body.detail ?? t('admin.err_status_code', { status: res.status }));
    }
    setDocuments([]);
    setPasswordModal(null);
  };

  const handleDeleteAllSessions = async (password: string) => {
    const res = await apiFetch(`${API_BASE_URL}/sessions/all`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({})) as { detail?: string };
      throw new Error(body.detail ?? t('admin.err_status_code', { status: res.status }));
    }
    setPasswordModal(null);
  };

  if (user?.role !== 'admin') {
    return <div className="p-4 text-center" role="alert">{t('admin.err_unauthorized')}</div>;
  }

  return (
    <div className="admin-page" style={{ overflowY: 'auto', minHeight: '100vh' }}>
      {/* Header */}
      <div className="admin-header">
        <div className="admin-header-left">
          <button
            onClick={() => navigate('/')}
            className="btn btn-ghost icon-button"
            aria-label={t('admin.aria_back')}
            id="admin-back-btn"
          >
            <ArrowLeft size={18} />
          </button>
          <div className="admin-icon-box">
            <Database size={20} color="#fff" strokeWidth={1.5} />
          </div>
          <div>
            <h1 className="text-xl font-bold">{t('admin.title')}</h1>
            <p className="text-sm text-faint mt-1">{t('admin.subtitle')}</p>
          </div>
        </div>
        <button
          onClick={() => { void loadDocuments(); }}
          className="btn btn-secondary"
          id="admin-refresh-btn"
        >
          <RefreshCw size={15} />
          <span>{t('admin.btn_reload')}</span>
        </button>
      </div>

      <div className="admin-content">
        {/* Upload Zone */}
        <div className="admin-card glass-panel">
          <div className="admin-card-header">
            <span className="admin-card-title">
              <UploadCloud size={16} />
              {t('admin.upload_btn')}
            </span>
          </div>
          <div className="admin-card-body">
            <input
              type="file" multiple accept=".pdf,.docx,.txt"
              onChange={handleFileInputChange}
              style={{ display: 'none' }} id="file-upload"
              disabled={isUploading}
            />
            <label
              htmlFor="file-upload"
              className={`upload-zone ${isDragging ? 'dragging' : ''}`}
              onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
            >
              {isUploading ? (
                <div className="flex flex-col items-center gap-3">
                  <Loader2 size={36} className="spin" style={{ color: 'var(--brown-400)' }} />
                  <p className="text-sm font-medium">{t('admin.upload_processing')}</p>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-3">
                  <UploadCloud size={36} className="text-faint" />
                  <div>
                    <p className="font-medium" style={{ color: 'var(--text)' }}>{t('admin.drag_drop')}</p>
                    <p className="text-sm text-muted mt-1">{t('admin.click_browse')}</p>
                  </div>
                  <div className="btn btn-primary pointer-events-none">{t('admin.select_file')}</div>
                  <p className="text-xs text-faint">{t('admin.upload_rules')}</p>
                </div>
              )}
            </label>
          </div>
        </div>

        {error && (
          <div className="error-banner animate-slide-up" role="alert" aria-live="assertive">{error}</div>
        )}

        {/* Documents Table */}
        <div className="admin-card glass-panel">
          <div className="admin-card-header">
            <span className="admin-card-title">
              <FileText size={16} />
              {t('admin.doc_list', { count: documents.length })}
            </span>
          </div>
          <div className="doc-table-wrap">
            {documents.length === 0 ? (
              <div className="admin-card-body">
                <div className="flex flex-col items-center gap-2 py-6 text-center">
                  <FileText size={28} className="text-faint" />
                  <p className="text-sm text-muted">{t('admin.empty')}</p>
                </div>
              </div>
            ) : (
              <table className="doc-table">
                <thead>
                  <tr>
                    <th>{t('admin.col_name')}</th>
                    <th>{t('admin.col_type')}</th>
                    <th>{t('admin.col_size')}</th>
                    <th style={{ textAlign: 'right' }}>{t('admin.col_action')}</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map(doc => (
                    <tr key={doc.filename}>
                      <td>
                        <div className="doc-filename">
                          <FileText size={15} style={{ color: 'var(--brown-400)', flexShrink: 0 }} />
                          <span className="truncate" style={{ maxWidth: '300px' }}>{doc.filename}</span>
                        </div>
                      </td>
                      <td>
                        <span className="doc-badge doc-badge-pdf">
                          {doc.filename.split('.').pop()?.toUpperCase() ?? 'FILE'}
                        </span>
                      </td>
                      <td>{formatBytes(doc.size_bytes)}</td>
                      <td style={{ textAlign: 'right' }}>
                        <button
                          className="btn btn-danger"
                          style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem' }}
                          onClick={() => void handleDeleteFile(doc.filename)}
                          disabled={deletingFile === doc.filename}
                          id={`delete-doc-${doc.filename}`}
                        >
                          {deletingFile === doc.filename
                            ? t('admin.deleting')
                            : <><Trash2 size={13} /> {t('admin.btn_delete')}</>}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Tasks */}
        {tasks.length > 0 && (
          <div className="admin-card glass-panel">
            <div className="admin-card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="admin-card-title">
                <Loader2 size={16} />
                {t('admin.bg_tasks')}
              </span>
              <button 
                className="btn btn-ghost" 
                style={{ padding: '0.2rem 0.5rem', fontSize: '0.75rem', height: 'auto' }}
                onClick={() => setTasks(prev => prev.filter(t => t.status === 'queued' || t.status === 'processing'))}
                title="Clear completed tasks"
              >
                <Trash2 size={13} style={{ marginRight: '4px', display: 'inline' }} />
                {t('common.clear', 'Clear')}
              </button>
            </div>
            <div className="admin-card-body flex-col gap-3" style={{ maxHeight: '300px', overflowY: 'auto' }}>
              {tasks.map(task => (
                <div key={task.task_id} className={`task-status ${task.status === 'completed' ? 'completed' : task.status === 'failed' ? 'failed' : 'queued'}`}>
                  <div className="flex items-center gap-2 shrink-0">
                    {(task.status === 'queued' || task.status === 'processing') && <Loader2 size={15} className="spin" />}
                    {task.status === 'completed' && <CheckCircle size={15} />}
                    {task.status === 'failed' && <XCircle size={15} />}
                    <span className="font-medium uppercase" style={{ fontSize: '0.75rem' }}>{task.status}</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <span className="text-xs truncate">
                      {task.type.toUpperCase()} • {task.meta.files?.join(', ') ?? `${task.meta.count ?? 0} files`}
                    </span>
                    {task.error && <p className="text-xs text-danger mt-1">{task.error}</p>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Danger Zone */}
        <div className="danger-zone">
          <div className="danger-zone-header">
            <AlertTriangle size={16} style={{ color: '#e74c3c' }} />
            <span className="danger-zone-title">{t('admin.danger_zone')}</span>
          </div>
          <div className="danger-zone-body">
            <div className="danger-zone-item">
              <div className="danger-zone-item-info">
                <p className="danger-zone-item-title">{t('admin.delete_all_docs')}</p>
                <p className="danger-zone-item-desc">{t('admin.delete_all_docs_desc')}</p>
              </div>
              <button
                className="btn btn-danger shrink-0"
                onClick={() => setPasswordModal('all-docs')}
                id="admin-delete-all-docs-btn"
              >
                <Trash2 size={14} />
                {t('admin.btn_delete_all_docs')}
              </button>
            </div>

            <div className="danger-zone-item">
              <div className="danger-zone-item-info">
                <p className="danger-zone-item-title">{t('admin.delete_all_chats')}</p>
                <p className="danger-zone-item-desc">{t('admin.delete_all_chats_desc')}</p>
              </div>
              <button
                className="btn btn-danger shrink-0"
                onClick={() => setPasswordModal('all-sessions')}
                id="admin-delete-all-sessions-btn"
              >
                <Trash2 size={14} />
                {t('admin.btn_delete_all_chats')}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Password Modals */}
      {passwordModal === 'all-docs' && (
        <PasswordModal
          title={t('admin.confirm_delete_all_docs_title')}
          description={t('admin.confirm_delete_all_docs_desc')}
          onConfirm={handleDeleteAllDocs}
          onCancel={() => setPasswordModal(null)}
        />
      )}
      {passwordModal === 'all-sessions' && (
        <PasswordModal
          title={t('admin.confirm_delete_all_chats_title')}
          description={t('admin.confirm_delete_all_chats_desc')}
          onConfirm={handleDeleteAllSessions}
          onCancel={() => setPasswordModal(null)}
        />
      )}
    </div>
  );
}
