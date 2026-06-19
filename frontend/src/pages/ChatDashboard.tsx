import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../context/auth';
import { API_BASE_URL } from '../config';
import Sidebar from '../components/Sidebar';
import { useChatStream, type SourceNode } from '../hooks/useChatStream';
import { Send, FileText, Scale, Menu, Square, Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
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
  const { sendMessage, isStreaming, cancelStream } = useChatStream();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const loadedSessionsRef = useRef(new Set<string>());
  const messages = useMemo(
    () => currentSessionId ? messagesBySession[currentSessionId] ?? [] : [],
    [currentSessionId, messagesBySession],
  );

  // Auto-resize textarea
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const ta = e.target;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 180)}px`;
  };

  // Load history
  useEffect(() => {
    if (!currentSessionId) return;
    const sessionId = currentSessionId;
    if (loadedSessionsRef.current.has(sessionId)) return;
    const controller = new AbortController();

    void apiFetch(`${API_BASE_URL}/sessions/${sessionId}/messages`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error(`Không thể tải lịch sử (${response.status})`);
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

  // Scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isStreaming || isLoadingHistory) return;

    let targetSessionId = currentSessionId;
    if (!targetSessionId) {
      try {
        const res = await apiFetch(`${API_BASE_URL}/sessions/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: 'Cuộc trò chuyện mới' }),
        });
        if (!res.ok) throw new Error('Cannot create session');
        const data = await res.json();
        const newSessionId = String(data.id);
        targetSessionId = newSessionId;
        loadedSessionsRef.current.add(newSessionId);
        setCurrentSessionId(newSessionId);
        setSessionsVersion(v => v + 1);
      } catch {
        setError('Không thể tạo cuộc trò chuyện mới.');
        return;
      }
    }

    const sessionId = targetSessionId as string;
    const userMessage = input.trim();

    // Reset textarea
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
    setError('');

    const messageKey = crypto.randomUUID();
    const tempUserMsg: Message = { id: `${messageKey}-user`, role: 'user', content: userMessage };
    const tempAssistantMsg: Message = { id: `${messageKey}-assistant`, role: 'assistant', content: '' };

    setMessagesBySession(previous => ({
      ...previous,
      [sessionId]: [...(previous[sessionId] ?? []), tempUserMsg, tempAssistantMsg],
    }));

    await sendMessage(
      sessionId,
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

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSubmit(e as unknown as React.FormEvent);
    }
  };

  const handleOpenSource = (filename: string, pageLabel: string | number) => {
    let docUrl = `${API_BASE_URL}/documents/file/${encodeURIComponent(filename)}`;
    if (filename.toLowerCase().endsWith('.pdf') && pageLabel && pageLabel !== 'N/A') {
      docUrl += `#page=${pageLabel}`;
    }
    const previewWindow = window.open(docUrl, '_blank', 'noopener,noreferrer');
    if (!previewWindow) {
      setError('Trình duyệt đã chặn popup. Vui lòng cho phép popup để xem tài liệu.');
    }
  };

  const renderSources = (sources?: SourceNode[]) => {
    if (!sources?.length) return null;
    return (
      <div className="sources-container">
        <p className="sources-label">Nguồn tham khảo</p>
        <div className="source-list">
          {sources.map((src, index) => {
            const filename = typeof src.metadata.file_name === 'string' ? src.metadata.file_name : '';
            const pageLabel = typeof src.metadata.page_label === 'string' || typeof src.metadata.page_label === 'number'
              ? src.metadata.page_label : 'N/A';
            return (
              <button
                key={`${filename}-${index}`}
                type="button"
                onClick={() => handleOpenSource(filename, pageLabel)}
                disabled={!filename}
                className="source-card"
              >
                <FileText size={13} className="shrink-0" />
                <span>
                  <span className="source-filename">{filename || 'Không rõ tài liệu'}</span>
                  <span style={{ color: 'var(--text-faint)', fontSize: '0.7rem' }}>Trang: {pageLabel}</span>
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
          cancelStream();
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
        {/* Mobile header */}
        <div className="mobile-header">
          <button
            type="button"
            className="btn btn-ghost icon-button"
            aria-label="Mở danh sách cuộc trò chuyện"
            onClick={() => setIsSidebarOpen(true)}
          >
            <Menu size={20} />
          </button>
          <Scale size={18} style={{ color: 'var(--brown-400)' }} />
          <span className="font-bold text-sm">Trợ Lý Pháp Lý</span>
        </div>

        {/* Chat area */}
        <div className="chat-area">
          {error && (
            <div
              className="error-banner mb-4 animate-slide-up"
              role="alert"
              aria-live="assertive"
            >{error}</div>
          )}

          {isLoadingHistory ? (
            <div className="flex items-center justify-center flex-1 gap-3 text-muted">
              <Loader2 size={20} className="spin" />
              <span className="text-sm">Đang tải lịch sử...</span>
            </div>
          ) : messages.length === 0 ? (
            <div className="welcome-state animate-fade-in">
              <div className="welcome-icon">
                <Scale size={30} color="#fff" strokeWidth={1.5} />
              </div>
              <h2 className="welcome-title">Trợ lý pháp lý AI</h2>
              <p className="welcome-sub">
                Đặt câu hỏi về pháp luật Việt Nam. Tôi sẽ tra cứu và tư vấn dựa trên cơ sở dữ liệu pháp luật hiện hành.
              </p>
            </div>
          ) : (
            <div className="message-list animate-fade-in">
              {messages.map(msg => (
                <div
                  key={msg.id}
                  className={`message-row ${msg.role === 'user' ? 'user-row' : ''}`}
                >
                  {msg.role === 'assistant' && (
                    <div className="message-avatar ai-avatar">
                      <Scale size={14} color="#fff" strokeWidth={1.8} />
                    </div>
                  )}
                  {msg.role === 'user' && (
                    <div className="message-avatar user-avatar-msg">
                      <span style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-muted)' }}>U</span>
                    </div>
                  )}

                  <div className={`message-bubble ${msg.role === 'user' ? 'user-message' : `ai-message ${msg.failed ? 'message-failed' : ''}`}`}>
                    {msg.role === 'assistant' && msg.content === '' && isStreaming ? (
                      <div className="thinking-dots">
                        <span /><span /><span />
                      </div>
                    ) : msg.role === 'assistant' ? (
                      <div className="prose">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                      </div>
                    ) : (
                      <div style={{ whiteSpace: 'pre-wrap', fontSize: '0.9rem' }}>{msg.content}</div>
                    )}
                    {msg.role === 'assistant' && renderSources(msg.sources)}
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input */}
        <div className="chat-input-wrapper">
          <form onSubmit={handleSubmit} className="chat-form" id="chat-form">
            <textarea
              ref={textareaRef}
              className="chat-textarea"
              placeholder="Nhập câu hỏi pháp lý... (Enter để gửi, Shift+Enter để xuống dòng)"
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              maxLength={4000}
              rows={1}
              disabled={isLoadingHistory}
              id="chat-input"
            />
            {isStreaming ? (
              <button
                type="button"
                onClick={cancelStream}
                className="chat-stop-btn"
                aria-label="Dừng sinh văn bản"
                id="chat-stop-btn"
              >
                <Square size={15} fill="currentColor" />
              </button>
            ) : (
              <button
                type="submit"
                className="chat-send-btn"
                aria-label="Gửi câu hỏi"
                disabled={!input.trim() || isLoadingHistory}
                id="chat-send-btn"
              >
                <Send size={15} />
              </button>
            )}
          </form>
          <p className="text-center text-xs text-faint mt-2">
            AI có thể mắc lỗi. Hãy kiểm tra thông tin pháp lý từ nguồn chính thức.
          </p>
        </div>
      </div>
    </div>
  );
}
