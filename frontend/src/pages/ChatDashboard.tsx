import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../context/auth';
import { API_BASE_URL } from '../config';
import Sidebar from '../components/Sidebar';
import { useChatStream, type SourceNode } from '../hooks/useChatStream';
import { Send, FileText, Bot, Menu } from 'lucide-react';
import { parseMessages } from '../utils/validation';

interface Message {
  id: string | number;
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceNode[];
  failed?: boolean;
}

export default function ChatDashboard() {
  const { apiFetch } = useAuth();
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [messagesBySession, setMessagesBySession] = useState<Record<string, Message[]>>({});
  const [input, setInput] = useState('');
  const [error, setError] = useState('');
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [sessionsVersion, setSessionsVersion] = useState(0);
  const { sendMessage, isStreaming } = useChatStream(currentSessionId);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const loadedSessionsRef = useRef(new Set<string>());
  const messages = useMemo(
    () => currentSessionId ? messagesBySession[currentSessionId] ?? [] : [],
    [currentSessionId, messagesBySession],
  );

  useEffect(() => {
    if (!currentSessionId) return;

    const sessionId = currentSessionId;
    if (loadedSessionsRef.current.has(sessionId)) {
      return;
    }

    const controller = new AbortController();

    void apiFetch(`${API_BASE_URL}/sessions/${sessionId}/messages`, {
      signal: controller.signal,
    })
      .then(async response => {
        if (!response.ok) {
          throw new Error(`Không thể tải lịch sử (${response.status})`);
        }
        return response.json();
      })
      .then(data => {
        loadedSessionsRef.current.add(sessionId);
        setMessagesBySession(previous => ({
          ...previous,
          [sessionId]: parseMessages(data),
        }));
        setError('');
        setIsLoadingHistory(false);
      })
      .catch(fetchError => {
        if (!controller.signal.aborted) {
          console.error(fetchError);
          setError('Không thể tải lịch sử cuộc trò chuyện.');
          setIsLoadingHistory(false);
        }
      });

    return () => controller.abort();
  }, [apiFetch, currentSessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isStreaming || isLoadingHistory || !currentSessionId) return;

    const sessionId = currentSessionId;
    const userMessage = input.trim();
    setInput('');
    setError('');
    
    // Optimistic update for user message
    const messageKey = crypto.randomUUID();
    const tempUserMsg: Message = { id: `${messageKey}-user`, role: 'user', content: userMessage };
    const tempAssistantMsg: Message = { id: `${messageKey}-assistant`, role: 'assistant', content: '' };
    
    setMessagesBySession(previous => ({
      ...previous,
      [sessionId]: [...(previous[sessionId] ?? []), tempUserMsg, tempAssistantMsg],
    }));

    await sendMessage(
      userMessage,
      (chunk) => {
        setMessagesBySession(previous => ({
          ...previous,
          [sessionId]: (previous[sessionId] ?? []).map(message =>
            message.id === tempAssistantMsg.id
              ? { ...message, content: message.content + chunk }
              : message
          ),
        }));
      },
      (sources) => {
        setMessagesBySession(previous => ({
          ...previous,
          [sessionId]: (previous[sessionId] ?? []).map(message =>
            message.id === tempAssistantMsg.id
              ? { ...message, sources }
              : message
          ),
        }));
      },
      (message) => {
        setMessagesBySession(previous => ({
          ...previous,
          [sessionId]: (previous[sessionId] ?? []).map(currentMessage =>
            currentMessage.id === tempAssistantMsg.id
              ? { ...currentMessage, content: message, failed: true }
              : currentMessage
          ),
        }));
      }
    );
    setSessionsVersion(version => version + 1);
  };

  const handleOpenSource = async (filename: string) => {
    const previewWindow = window.open('about:blank', '_blank', 'noopener,noreferrer');
    if (previewWindow) previewWindow.opener = null;

    try {
      const response = await apiFetch(
        `${API_BASE_URL}/documents/file/${encodeURIComponent(filename)}`,
      );

      if (!response.ok) {
        throw new Error(`Document request failed with status ${response.status}`);
      }

      const blobUrl = URL.createObjectURL(await response.blob());
      if (previewWindow) {
        previewWindow.location.href = blobUrl;
      } else {
        const link = document.createElement('a');
        link.href = blobUrl;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.click();
      }

      window.setTimeout(() => URL.revokeObjectURL(blobUrl), 300_000);
    } catch (error) {
      previewWindow?.close();
      console.error(error);
      setError('Không thể mở tài liệu nguồn.');
    }
  };

  const renderSources = (sources?: SourceNode[]) => {
    if (!sources?.length) return null;
      
    return (
      <div className="mt-2 flex-col gap-2">
        <p className="text-xs font-bold text-muted">Nguồn tham khảo:</p>
        <div className="source-list">
          {sources.map((src, index) => {
            const filename = typeof src.metadata.file_name === 'string'
              ? src.metadata.file_name
              : '';
            const pageLabel = typeof src.metadata.page_label === 'string'
              || typeof src.metadata.page_label === 'number'
              ? src.metadata.page_label
              : 'N/A';

            return (
              <button
                key={`${filename}-${index}`}
                type="button"
                onClick={() => handleOpenSource(filename)}
                disabled={!filename}
                className="glass source-card"
              >
                <FileText size={16} className="text-muted" />
                <span className="flex-col">
                  <span className="text-xs font-bold truncate source-filename">
                    {filename || 'Không rõ tài liệu'}
                  </span>
                  <span className="text-xs text-muted">Trang: {pageLabel}</span>
                </span>
              </button>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div className="app-container">
      <Sidebar
        currentSessionId={currentSessionId}
        onSelectSession={sessionId => {
          setCurrentSessionId(sessionId);
          setIsLoadingHistory(Boolean(sessionId && !loadedSessionsRef.current.has(sessionId)));
          setInput('');
          setError('');
          setIsSidebarOpen(false);
        }}
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
        refreshKey={sessionsVersion}
      />
      {isSidebarOpen && (
        <button
          type="button"
          className="sidebar-overlay"
          aria-label="Đóng danh sách cuộc trò chuyện"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}
      
      <div className="main-content">
        <div className="mobile-header">
          <button
            type="button"
            className="btn btn-ghost icon-button"
            aria-label="Mở danh sách cuộc trò chuyện"
            onClick={() => setIsSidebarOpen(true)}
          >
            <Menu size={20} />
          </button>
          <span className="font-bold">Trợ Lý Pháp Lý</span>
        </div>
        <div className="flex-1 p-4" style={{ overflowY: 'auto' }}>
          {error && <div className="error-banner mb-4" role="alert" aria-live="assertive">{error}</div>}
          {isLoadingHistory ? (
            <div className="h-full flex items-center justify-center text-muted">
              Đang tải lịch sử...
            </div>
          ) : messages.length === 0 ? (
            <div className="h-full flex items-center justify-center flex-col text-muted">
              <Bot size={48} className="mb-4 opacity-50" />
              <p>Chọn một cuộc trò chuyện ở bên trái hoặc tạo mới để bắt đầu.</p>
            </div>
          ) : (
            <div className="message-list">
              {messages.map(msg => (
                <div key={msg.id} className={`flex gap-4 ${msg.role === 'user' ? 'justify-end' : ''}`}>
                  {msg.role === 'assistant' && (
                    <div className="w-8 h-8 rounded-full glass flex items-center justify-center shrink-0 mt-2">
                      <Bot size={16} color="hsl(var(--primary))" />
                    </div>
                  )}
                  <div className={`message-bubble ${msg.role === 'user' ? 'user-message' : 'glass-panel'} ${msg.failed ? 'message-failed' : ''}`}>
                    <div style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div>
                    {msg.role === 'assistant' && renderSources(msg.sources)}
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        <div className="p-4 bg-background" style={{ borderTop: '1px solid hsl(var(--border))' }}>
          <form onSubmit={handleSubmit} className="chat-form">
            <input
              type="text"
              className="input flex-1"
              placeholder={currentSessionId ? "Nhập câu hỏi pháp lý..." : "Vui lòng chọn hoặc tạo mới phiên chat..."}
              value={input}
              onChange={e => setInput(e.target.value)}
              maxLength={4000}
              disabled={!currentSessionId || isStreaming || isLoadingHistory}
            />
            <button 
              type="submit" 
              className="btn btn-primary rounded p-2"
              aria-label="Gửi câu hỏi"
              disabled={!currentSessionId || !input.trim() || isStreaming || isLoadingHistory}
            >
              <Send size={18} />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
