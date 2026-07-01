import { useCallback, useEffect, useState } from 'react';
import {
  Loader2, UploadCloud, Trash2, AlertTriangle, 
  RefreshCw, Eye, Edit3, ChevronLeft, ChevronRight
} from 'lucide-react';
import { API_BASE_URL, UPLOAD_MAX_FILE_BYTES, UPLOAD_MAX_FILES, UPLOAD_MAX_TOTAL_BYTES, UPLOAD_TIMEOUT_MS } from '../../config';
import { useAuth } from '../../context/auth';
import { useTranslation } from 'react-i18next';
import ConfirmDialog from '../../components/ConfirmDialog';
import { useNavigate } from 'react-router-dom';

interface Task {
  task_id: string; type: string; status: 'queued' | 'processing' | 'completed' | 'failed';
  meta: { files?: string[]; count?: number }; error?: string; updated_at: number;
}
interface DocumentInfo { filename: string; size_bytes: number; }
interface DocumentListResponse { documents: DocumentInfo[]; total: number; }
interface IngestResponse { task_id: string; files?: string[]; }
interface ErrorResponse { detail?: string; }

const TASK_STORAGE_PREFIX = 'local-rag-assistant-admin-tasks';
function storageKey(username: string) { return `${TASK_STORAGE_PREFIX}:${username}`; }

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024, sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function getErrorMessage(error: unknown, fallback = 'Error') {
  return error instanceof Error ? error.message : fallback;
}

export default function DocumentsTab() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { apiFetch, user } = useAuth();
  const username = user?.username ?? 'anonymous';
  const [tasks, setTasks] = useState<Task[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState('');
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [deletingFile, setDeletingFile] = useState<string | null>(null);
  const [pendingDeleteFile, setPendingDeleteFile] = useState<string | null>(null);
  const [notice, setNotice] = useState('');

  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 10;

  const [previewDoc, setPreviewDoc] = useState<{ filename: string, text: string, isPdf?: boolean } | null>(null);

  const [passwordModal, setPasswordModal] = useState(false);

  const loadDocuments = useCallback(async () => {
    try {
      const skip = (page - 1) * pageSize;
      const res = await apiFetch(`${API_BASE_URL}/documents/?skip=${skip}&limit=${pageSize}`);
      if (res.ok) {
        const data = await res.json() as DocumentListResponse;
        setDocuments(data.documents.map(d => ({ filename: String(d.filename), size_bytes: Number(d.size_bytes) })));
        setTotal(data.total);
      }
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }, [apiFetch, page, pageSize]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadDocuments(), 0);
    return () => window.clearTimeout(timer);
  }, [loadDocuments]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        const parsed = JSON.parse(localStorage.getItem(storageKey(username)) ?? '[]');
        setTasks(Array.isArray(parsed) ? parsed : []);
      } catch {
        setTasks([]);
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [username]);

  const runningTaskIds = tasks
    .filter(task => task.status === 'queued' || task.status === 'processing')
    .map(task => task.task_id)
    .join('|');

  useEffect(() => {
    const taskIds = runningTaskIds.split('|').filter(Boolean);
    if (taskIds.length === 0) return;

    const pollTasks = async () => {
      const results = await Promise.all(taskIds.map(async taskId => {
        try {
          const res = await apiFetch(`${API_BASE_URL}/documents/tasks/${taskId}`);
          if (!res.ok) return null;
          return await res.json() as Task;
        } catch {
          return null;
        }
      }));
      const updatedTasks = results.filter((task): task is Task => task !== null);
      if (updatedTasks.length === 0) return;

      setTasks(current => {
        const byId = new Map(updatedTasks.map(task => [task.task_id, { ...task, updated_at: Date.now() }]));
        const next = current.map(task => byId.get(task.task_id) ?? task);
        localStorage.setItem(storageKey(username), JSON.stringify(next));
        return next;
      });

      if (updatedTasks.some(task => task.status === 'completed')) {
        void loadDocuments();
      }
    };

    void pollTasks();
    const interval = window.setInterval(() => void pollTasks(), 3000);
    return () => window.clearInterval(interval);
  }, [apiFetch, loadDocuments, runningTaskIds, username]);

  const processUpload = async (files: File[]) => {
    const totalBytes = files.reduce((s, f) => s + f.size, 0);
    const oversized = files.filter(f => f.size > UPLOAD_MAX_FILE_BYTES).map(f => f.name);
    if (files.length > UPLOAD_MAX_FILES) { setError(t('admin.err_max_files', { count: UPLOAD_MAX_FILES })); return; }
    if (oversized.length > 0 || totalBytes > UPLOAD_MAX_TOTAL_BYTES) {
      setError(oversized.length > 0 ? `${t('admin.err_file_limits')} ${oversized.join(', ')}` : t('admin.err_file_limits'));
      return;
    }
    setIsUploading(true); setError(''); setNotice('');
    const fd = new FormData();
    files.forEach(f => fd.append('files', f));
    try {
      const res = await apiFetch(`${API_BASE_URL}/documents/ingest`, { method: 'POST', body: fd, timeoutMs: UPLOAD_TIMEOUT_MS });
      if (!res.ok) {
        const body = await res.json().catch(() => ({})) as ErrorResponse;
        throw new Error(body.detail ?? t('admin.err_cannot_upload'));
      }
      const data = await res.json() as IngestResponse;
      const newTask: Task = { task_id: data.task_id, type: 'ingest', status: 'queued', meta: { files: data.files }, updated_at: Date.now() };
      setTasks(current => {
        const next = [newTask, ...current];
        localStorage.setItem(storageKey(username), JSON.stringify(next));
        return next;
      });
      setNotice(t('admin.upload_queued', 'Upload queued for processing.'));
      loadDocuments();
    } catch (err) { setError(getErrorMessage(err)); }
    finally { setIsUploading(false); }
  };

  const handleDeleteFile = async (filename: string) => {
    setNotice('');
    setDeletingFile(filename);
    try {
      const res = await apiFetch(`${API_BASE_URL}/documents/${encodeURIComponent(filename)}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(t('admin.err_cannot_delete'));
      setDocuments(p => p.filter(d => d.filename !== filename));
      setTotal(p => Math.max(0, p - 1));
      setNotice(t('admin.delete_success', 'Deleted successfully.'));
    } catch (err) { setError(getErrorMessage(err)); }
    finally { setDeletingFile(null); setPendingDeleteFile(null); }
  };

  const handlePreview = async (filename: string) => {
    setPreviewDoc(null);
    if (filename.toLowerCase().endsWith('.pdf')) {
      setPreviewDoc({ filename, text: '', isPdf: true });
      return;
    }
    try {
      const res = await apiFetch(`${API_BASE_URL}/documents/${encodeURIComponent(filename)}/preview`);
      if (!res.ok) throw new Error('Failed to load preview');
      const data = await res.json() as { text: string };
      setPreviewDoc({ filename, text: data.text });
    } catch (err) { setError(getErrorMessage(err)); }
  };

  const handleDeleteAllDocs = async (password: string) => {
    setError('');
    setNotice('');
    const res = await apiFetch(`${API_BASE_URL}/documents/all`, {
      method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password })
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({})) as ErrorResponse;
      throw new Error(body.detail ?? 'Error');
    }
    setDocuments([]);
    setTotal(0);
    setPasswordModal(false);
    setNotice(t('admin.delete_success', 'Deleted successfully.'));
  };

  const totalPages = Math.ceil(total / pageSize);
  const paginatedDocs = documents;

  return (
    <>
      <div className="admin-page-header">
        <div>
          <h2 className="admin-page-title">{t('admin.title')}</h2>
          <p className="admin-page-subtitle">{t('admin.subtitle')}</p>
        </div>
        <button className="btn btn-secondary" onClick={loadDocuments}><RefreshCw size={15}/> {t('admin.btn_reload')}</button>
      </div>

      <div className="admin-page-body">
        {/* Quick Stats & Upload Grid */}
        <div className="admin-stats-grid cols-xl-3">
          {/* Quick Stats */}
          <div className="flex flex-col gap-6">
            <div className="glass-panel p-6 flex flex-col justify-center items-center h-full">
              <span className="text-3xl font-bold text-primary">{documents.length}</span>
              <span className="text-sm text-faint uppercase tracking-wider mt-1">{t('admin.page_documents', 'Documents on this page')}</span>
            </div>
            <div className="glass-panel p-6 flex flex-col justify-center items-center h-full">
              <span className="text-3xl font-bold text-success">
                {formatBytes(documents.reduce((acc, curr) => acc + curr.size_bytes, 0))}
              </span>
              <span className="text-sm text-faint uppercase tracking-wider mt-1">{t('admin.page_size', 'Size on this page')}</span>
            </div>
          </div>

          {/* Upload Zone */}
          <div className="glass-panel p-6 border-dashed border-2 flex flex-col items-center justify-center min-h-[160px] upload-zone" style={{ gridColumn: 'span 2', borderColor: 'var(--border-hover)' }}>
            <input type="file" multiple accept=".pdf,.docx,.txt" id="file-upload" className="hidden" onChange={e => e.target.files && processUpload(Array.from(e.target.files))} disabled={isUploading}/>
            <label htmlFor="file-upload" className={`w-full h-full cursor-pointer flex flex-col items-center justify-center p-4 gap-3 transition-all ${isDragging ? 'opacity-50' : 'hover:opacity-80'}`} onDragOver={e => { e.preventDefault(); setIsDragging(true); }} onDragLeave={() => setIsDragging(false)} onDrop={e => { e.preventDefault(); setIsDragging(false); processUpload(Array.from(e.dataTransfer.files)); }}>
              {isUploading ? (
                <>
                  <Loader2 size={40} className="spin text-primary" />
                  <p className="text-primary font-medium mt-2">{t('admin.uploading_ingesting')}</p>
                </>
              ) : (
                <>
                  <div className="w-16 h-16 rounded-full flex items-center justify-center mb-2" style={{ background: 'var(--bg-overlay)', color: 'var(--primary)' }}>
                    <UploadCloud size={32}/>
                  </div>
                  <p className="font-medium text-text text-lg">{t('admin.drag_drop_upload')}</p>
                  <p className="text-xs text-faint">{t('admin.upload_limits')}</p>
                </>
              )}
            </label>
          </div>
        </div>

        {notice && <div className="success-banner">{notice}</div>}
        {error && <div className="error-banner">{error}</div>}

        {tasks.length > 0 && (
          <div className="glass-panel admin-task-panel">
            <div className="admin-task-header">
              <span>{t('admin.bg_tasks')}</span>
              <button className="btn btn-ghost text-xs py-1" onClick={() => {
                setTasks([]);
                localStorage.removeItem(storageKey(username));
              }}>{t('admin.clear_tasks', 'Clear')}</button>
            </div>
            <div className="admin-task-list">
              {tasks.slice(0, 5).map(task => (
                <div key={task.task_id} className={`task-status ${task.status}`}>
                  <span className="task-status-dot" />
                  <div className="task-status-copy">
                    <strong>{task.meta.files?.join(', ') || task.type}</strong>
                    <span>{task.status}{task.error ? `: ${task.error}` : ''}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="doc-table-wrap">
          <table className="doc-table">
            <thead>
              <tr><th>{t('admin.col_name')}</th><th>{t('admin.col_type')}</th><th>{t('admin.col_size')}</th><th style={{ textAlign: 'right' }}>{t('admin.col_action')}</th></tr>
            </thead>
            <tbody>
              {paginatedDocs.length === 0 ? <tr><td colSpan={4} className="text-center py-6 text-muted">{t('admin.empty')}</td></tr> : paginatedDocs.map(d => (
                <tr key={d.filename}>
                  <td className="font-medium truncate max-w-xs">{d.filename}</td>
                  <td><span className="badge-primary">{d.filename.split('.').pop()?.toUpperCase()}</span></td>
                  <td className="text-sm font-mono text-faint">{formatBytes(d.size_bytes)}</td>
                  <td className="text-right">
                    <div className="flex justify-end gap-2">
                      <button className="btn btn-secondary py-1 px-2 text-xs" onClick={() => handlePreview(d.filename)} title={t('admin.preview')}><Eye size={14}/></button>
                      <button className="btn btn-secondary py-1 px-2 text-xs" onClick={() => navigate(`/admin/documents/${encodeURIComponent(d.filename)}/chunks`)} title={t('admin.chunks')}><Edit3 size={14}/> {t('admin.chunks')}</button>
                      <button className="btn btn-danger py-1 px-2 text-xs" onClick={() => setPendingDeleteFile(d.filename)} disabled={deletingFile === d.filename} title={t('admin.btn_delete')}><Trash2 size={14}/></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        
        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex justify-center items-center gap-4 mt-2">
            <button className="btn btn-secondary px-3 py-1" disabled={page <= 1} onClick={() => setPage(p => p - 1)}><ChevronLeft size={16} /></button>
            <span className="text-sm font-medium text-muted">{t('admin.page_of', { page, total: totalPages })}</span>
            <button className="btn btn-secondary px-3 py-1" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}><ChevronRight size={16} /></button>
          </div>
        )}

        <div className="danger-zone mt-8">
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
              <button className="btn btn-danger shrink-0" onClick={() => setPasswordModal(true)}>
                <Trash2 size={14} /> {t('admin.btn_delete_all_docs')}
              </button>
            </div>
          </div>
        </div>
      </div>

      {previewDoc && (
        <div className="dialog-backdrop" onClick={() => setPreviewDoc(null)}>
          <div className="glass-panel w-full max-w-4xl h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="p-4 border-b border-default flex justify-between items-center shrink-0">
              <h3 className="font-bold text-lg">{t('admin.preview')}: {previewDoc.filename}</h3>
              <button className="btn btn-ghost px-3 py-1" onClick={() => setPreviewDoc(null)}>{t('sidebar.btn_close')}</button>
            </div>
            {previewDoc.isPdf ? (
              <div className="flex-1 min-h-0 bg-white">
                <iframe src={`${API_BASE_URL}/documents/file/${encodeURIComponent(previewDoc.filename)}`} className="w-full h-full border-none" title={t('chat.pdf_viewer_title')} />
              </div>
            ) : (
              <div className="p-6 flex-1 min-h-0 overflow-y-auto whitespace-pre-wrap font-mono text-sm leading-relaxed">{previewDoc.text}</div>
            )}
          </div>
        </div>
      )}

      {passwordModal && (
        <div className="dialog-backdrop" onClick={() => setPasswordModal(false)}>
          <div className="glass-panel dialog-panel" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-3 mb-2">
              <AlertTriangle size={24} className="text-danger" />
              <h3 className="dialog-title text-danger">{t('admin.confirm_delete_all_docs_title')}</h3>
            </div>
            <form onSubmit={e => {
              e.preventDefault();
              const fd = new FormData(e.currentTarget);
              handleDeleteAllDocs(fd.get('password') as string).catch(err => setError(err.message));
            }}>
              <div className="mb-4">
                <label className="input-label">{t('admin.admin_pwd')}</label>
                <input type="password" name="password" className="input" required />
              </div>
              <div className="dialog-actions">
                <button type="button" className="btn btn-ghost" onClick={() => setPasswordModal(false)}>{t('common.cancel')}</button>
                <button type="submit" className="btn btn-danger">{t('common.confirm')}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {pendingDeleteFile && (
        <ConfirmDialog
          title={t('admin.confirm_delete_file_title', 'Delete document?')}
          message={t('admin.confirm_delete_file_desc', { filename: pendingDeleteFile, defaultValue: `Delete "${pendingDeleteFile}"? This action cannot be undone.` })}
          onConfirm={() => void handleDeleteFile(pendingDeleteFile)}
          onCancel={() => setPendingDeleteFile(null)}
          confirmLabel={t('admin.btn_delete')}
        />
      )}
    </>
  );
}
