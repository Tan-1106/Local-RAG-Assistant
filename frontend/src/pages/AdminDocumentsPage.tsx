import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, CheckCircle, Loader2, UploadCloud, XCircle } from 'lucide-react';
import {
  API_BASE_URL,
  UPLOAD_MAX_FILE_BYTES,
  UPLOAD_MAX_FILES,
  UPLOAD_MAX_TOTAL_BYTES,
  UPLOAD_TIMEOUT_MS,
} from '../config';
import { useAuth } from '../context/auth';

interface Task {
  task_id: string;
  type: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  meta: {
    files?: string[];
    count?: number;
  };
  error?: string;
  updated_at: number;
}

const TASK_STORAGE_PREFIX = 'legal-assistant-admin-tasks';
const TASK_RETENTION_MS = 24 * 60 * 60 * 1000;
const ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.txt'];

function storageKey(username: string) {
  return `${TASK_STORAGE_PREFIX}:${username}`;
}

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
  ) {
    return null;
  }
  return candidate as Task;
}

function loadStoredTasks(username: string): Task[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(storageKey(username)) ?? '[]');
    if (!Array.isArray(parsed)) return [];
    const cutoff = Date.now() - TASK_RETENTION_MS;
    return parsed
      .map(parseTask)
      .filter((task): task is Task => Boolean(task && task.updated_at >= cutoff))
      .slice(0, 50);
  } catch {
    return [];
  }
}

function taskFromResponse(value: unknown, current: Task): Task {
  if (!value || typeof value !== 'object') {
    throw new Error('Invalid task response');
  }
  const response = value as Record<string, unknown>;
  const status = response.status;
  if (!['queued', 'processing', 'completed', 'failed'].includes(String(status))) {
    throw new Error('Unknown task status');
  }
  const meta = response.meta && typeof response.meta === 'object'
    ? response.meta as Task['meta']
    : current.meta;
  return {
    ...current,
    status: status as Task['status'],
    meta,
    error: typeof response.error === 'string' && response.error
      ? response.error
      : undefined,
    updated_at: Date.now(),
  };
}

export default function AdminDocumentsPage() {
  const { user, apiFetch } = useAuth();
  const navigate = useNavigate();
  const username = user?.username ?? 'anonymous';
  const [tasks, setTasks] = useState<Task[]>(() => loadStoredTasks(username));
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState('');
  const activeTaskKey = useMemo(
    () => tasks
      .filter(task => task.status === 'queued' || task.status === 'processing')
      .map(task => task.task_id)
      .sort()
      .join('|'),
    [tasks],
  );

  useEffect(() => {
    try {
      localStorage.setItem(storageKey(username), JSON.stringify(tasks.slice(0, 50)));
    } catch (storageError) {
      console.error('Could not persist task history', storageError);
    }
  }, [tasks, username]);

  useEffect(() => {
    if (!activeTaskKey) return;
    const activeTaskIds = activeTaskKey.split('|');
    const controller = new AbortController();
    let timer: number | undefined;

    const poll = async () => {
      for (const taskId of activeTaskIds) {
        if (controller.signal.aborted) return;
        try {
          const response = await apiFetch(
            `${API_BASE_URL}/documents/tasks/${encodeURIComponent(taskId)}`,
            { signal: controller.signal },
          );
          if (response.ok) {
            const data: unknown = await response.json();
            setTasks(previous => previous.map(item =>
              item.task_id === taskId ? taskFromResponse(data, item) : item
            ));
          } else if (response.status === 404) {
            setTasks(previous => previous.map(item =>
              item.task_id === taskId
                ? { ...item, status: 'failed', error: 'Job đã hết hạn hoặc không tồn tại.', updated_at: Date.now() }
                : item
            ));
          } else if (response.status === 401 || response.status === 403) {
            setError('Phiên quản trị đã hết hạn hoặc không còn quyền truy cập.');
          } else if (response.status === 429) {
            setError('Đang kiểm tra trạng thái quá nhanh. Hệ thống sẽ thử lại.');
          } else {
            setError(`Không thể kiểm tra trạng thái job (${response.status}).`);
          }
        } catch (pollError) {
          if (!controller.signal.aborted) {
            console.error(pollError);
            setError('Tạm thời không thể kiểm tra trạng thái job.');
          }
        }
      }
      if (!controller.signal.aborted) timer = window.setTimeout(poll, 2000);
    };

    void poll();
    return () => {
      controller.abort();
      if (timer) window.clearTimeout(timer);
    };
  }, [activeTaskKey, apiFetch]);

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const input = event.currentTarget;
    if (!input.files?.length) return;

    const selectedFiles = Array.from(input.files);
    const unsupportedFiles = selectedFiles.filter(file =>
      !ALLOWED_EXTENSIONS.some(extension => file.name.toLowerCase().endsWith(extension))
    );
    const oversizedFiles = selectedFiles.filter(file => file.size > UPLOAD_MAX_FILE_BYTES);
    const totalBytes = selectedFiles.reduce((total, file) => total + file.size, 0);

    if (selectedFiles.length > UPLOAD_MAX_FILES) {
      setError(`Chỉ được tải tối đa ${UPLOAD_MAX_FILES} tệp mỗi lần.`);
      input.value = '';
      return;
    }
    if (unsupportedFiles.length > 0) {
      setError(`Không hỗ trợ: ${unsupportedFiles.map(file => file.name).join(', ')}`);
      input.value = '';
      return;
    }
    if (oversizedFiles.length > 0 || totalBytes > UPLOAD_MAX_TOTAL_BYTES) {
      setError('Tệp vượt quá giới hạn 10 MB/tệp hoặc 50 MB/tổng.');
      input.value = '';
      return;
    }

    setIsUploading(true);
    setError('');
    const formData = new FormData();
    selectedFiles.forEach(file => formData.append('files', file));

    try {
      const response = await apiFetch(`${API_BASE_URL}/documents/ingest`, {
        method: 'POST',
        body: formData,
        retryOnAuth: false,
        timeoutMs: UPLOAD_TIMEOUT_MS,
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null) as { detail?: string } | null;
        throw new Error(detail?.detail ?? `Tải tài liệu thất bại (${response.status}).`);
      }
      const data = await response.json() as Record<string, unknown>;
      if (
        typeof data.task_id !== 'string'
        || !Array.isArray(data.files)
        || !data.files.every(filename => typeof filename === 'string')
      ) {
        throw new Error('Phản hồi enqueue không hợp lệ.');
      }
      const queuedTask: Task = {
        task_id: data.task_id as string,
        type: 'ingest',
        status: 'queued',
        meta: { files: data.files as string[] },
        updated_at: Date.now(),
      };
      setTasks(previous => [queuedTask, ...previous].slice(0, 50));
    } catch (uploadError) {
      console.error(uploadError);
      setError(uploadError instanceof Error ? uploadError.message : 'Không thể tải tài liệu.');
    } finally {
      setIsUploading(false);
      input.value = '';
    }
  };

  if (user?.role !== 'admin') {
    return <div className="p-4 text-center" role="alert">Bạn không có quyền truy cập trang này.</div>;
  }

  return (
    <div className="app-container flex-col p-8" style={{ overflowY: 'auto' }}>
      <div className="flex items-center gap-4 mb-8">
        <button onClick={() => navigate('/')} className="btn btn-ghost p-2 rounded-full" aria-label="Quay lại">
          <ArrowLeft size={24} />
        </button>
        <h1 className="text-2xl font-bold">Quản Trị Tài Liệu RAG</h1>
      </div>

      <div className="glass-panel p-8 mb-8 text-center" style={{ borderStyle: 'dashed' }}>
        <input
          type="file"
          multiple
          accept=".pdf,.docx,.txt"
          onChange={handleFileUpload}
          style={{ display: 'none' }}
          id="file-upload"
          disabled={isUploading}
        />
        <label htmlFor="file-upload" className="flex flex-col items-center cursor-pointer">
          <UploadCloud size={48} className="text-muted mb-4" />
          <h3 className="text-lg font-bold mb-2">Tải tài liệu pháp luật lên hệ thống</h3>
          <p className="text-sm text-muted">PDF, DOCX, TXT. Tối đa 10 MB/tệp và 50 MB/lần tải.</p>
          <div className="btn btn-primary mt-4 pointer-events-none">
            {isUploading ? 'Đang tải lên...' : 'Chọn Tệp Bắt Đầu'}
          </div>
        </label>
      </div>

      {error && <div className="error-banner mb-4" role="alert" aria-live="assertive">{error}</div>}
      <h2 className="text-lg font-bold mb-4">Tiến trình xử lý nền (RQ Jobs)</h2>
      <div className="flex-col gap-4">
        {tasks.length === 0 ? (
          <p className="text-sm text-muted">Chưa có job nào được thực thi.</p>
        ) : tasks.map(task => (
          <div key={task.task_id} className="glass-panel p-4 flex items-center justify-between">
            <div className="flex-col">
              <span className="text-sm font-bold">Job ID: <span className="text-muted font-normal">{task.task_id}</span></span>
              <span className="text-xs text-muted mt-1">
                Loại: {task.type.toUpperCase()} | Files: {task.meta.files?.join(', ') ?? task.meta.count ?? 0}
              </span>
              {task.error && <span className="text-xs text-danger mt-1">Lỗi: {task.error}</span>}
            </div>
            <div className="flex items-center gap-2">
              {(task.status === 'queued' || task.status === 'processing') && (
                <Loader2 size={18} className="text-primary spin" />
              )}
              {task.status === 'completed' && <CheckCircle size={18} style={{ color: 'green' }} />}
              {task.status === 'failed' && <XCircle size={18} className="text-danger" />}
              <span className="text-sm font-bold uppercase">{task.status}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
