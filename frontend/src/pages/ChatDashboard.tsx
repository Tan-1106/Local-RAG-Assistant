import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { useAuth } from '../context/auth';
import { API_BASE_URL } from '../config';
import Sidebar from '../components/Sidebar';
import { useChatStream, type SourceNode } from '../hooks/useChatStream';
import { Send, FileText, Scale, Menu, Square, Loader2, X, ExternalLink } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { parseMessages } from '../utils/validation';
import { useTranslation } from 'react-i18next';

interface Message {
  id: string | number;
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceNode[];
  failed?: boolean;
}

export default function ChatDashboard() {
  const { t } = useTranslation();
  const { apiFetch } = useAuth();
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [messagesBySession, setMessagesBySession] = useState<Record<string, Message[]>>({});
  const [input, setInput] = useState('');
  const [error, setError] = useState('');
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [sessionsVersion, setSessionsVersion] = useState(0);
  const [selectedPdfUrl, setSelectedPdfUrl] = useState<string | null>(null);
  const [selectedPdfTitle, setSelectedPdfTitle] = useState<string>('');
  const [pdfPaneWidth, setPdfPaneWidth] = useState<number>(500);
  const [isDraggingPdf, setIsDraggingPdf] = useState(false);
  const isDraggingPdfRef = useRef(false);

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
        if (!response.ok) throw new Error(`${t('sidebar.err_load')} (${response.status})`);
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
          setError(t('sidebar.err_load'));
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
          body: JSON.stringify({ title: t('sidebar.new_chat') }),
        });
        if (!res.ok) throw new Error('Cannot create session');
        const data = await res.json();
        const newSessionId = String(data.id);
        targetSessionId = newSessionId;
        loadedSessionsRef.current.add(newSessionId);
        setCurrentSessionId(newSessionId);
        setSessionsVersion(v => v + 1);
      } catch {
        setError(t('sidebar.err_create'));
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
        // Safety filter: strip any leaked internal [SYS:N] reference tags
        const cleanChunk = chunk.replace(/\[SYS:\d+\]\s*/g, '');
        setMessagesBySession(previous => ({
          ...previous,
          [sessionId]: (previous[sessionId] ?? []).map(message =>
            message.id === tempAssistantMsg.id
              ? { ...message, content: message.content + cleanChunk }
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

  const handleMouseDownPdfResize = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isDraggingPdfRef.current = true;
    setIsDraggingPdf(true);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    const handleMouseMove = (mouseEvent: MouseEvent) => {
      if (!isDraggingPdfRef.current) return;
      // The pane is on the right, so its width is window width minus mouse X position
      const newWidth = window.innerWidth - mouseEvent.clientX;
      if (newWidth > 300 && newWidth < window.innerWidth - 300) {
        setPdfPaneWidth(newWidth);
      }
    };

    const handleMouseUp = () => {
      isDraggingPdfRef.current = false;
      setIsDraggingPdf(false);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  }, []);

  const handleOpenSource = (filename: string, pageLabel: string | number) => {
    let docUrl = `${API_BASE_URL}/documents/file/${encodeURIComponent(filename)}`;
    if (filename.toLowerCase().endsWith('.pdf')) {
      if (pageLabel && pageLabel !== 'N/A') {
        docUrl += `#page=${pageLabel}`;
      }
      setSelectedPdfUrl(docUrl);
      setSelectedPdfTitle(filename);
    } else {
      const previewWindow = window.open(docUrl, '_blank', 'noopener,noreferrer');
      if (!previewWindow) {
        setError(t('chat.err_blocked'));
      }
    }
  };

  const renderSources = (sources?: SourceNode[]) => {
    if (!sources?.length) return null;
    return (
      <div className="sources-container">
        <p className="sources-label">{t('chat.sources_label')}</p>
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
                  <span className="source-filename">{filename || 'Unknown'}</span>
                  <span style={{ color: 'var(--text-faint)', fontSize: '0.7rem' }}>{t('chat.source_page', { page: pageLabel })}</span>
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
          aria-label={t('chat.aria_close_sidebar')}
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      <div className="main-content">
        {/* Mobile header */}
        <div className="mobile-header">
          <button
            type="button"
            className="btn btn-ghost icon-button"
            aria-label={t('chat.aria_open_sidebar')}
            onClick={() => setIsSidebarOpen(true)}
          >
            <Menu size={20} />
          </button>
          <Scale size={18} style={{ color: 'var(--brown-400)' }} />
          <span className="font-bold text-sm">{t('chat.title')}</span>
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
              <span className="text-sm">{t('chat.loading_history')}</span>
            </div>
          ) : messages.length === 0 ? (
            <div className="welcome-state animate-fade-in">
              <div className="welcome-icon">
                <Scale size={30} color="#fff" strokeWidth={1.5} />
              </div>
              <h2 className="welcome-title">{t('chat.title')}</h2>
              <p className="welcome-sub">
                {t('chat.input_placeholder')}
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
              placeholder={t('chat.input_placeholder')}
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
                aria-label={t('chat.aria_stop_generation')}
                id="chat-stop-btn"
              >
                <Square size={15} fill="currentColor" />
              </button>
            ) : (
              <button
                type="submit"
                className="chat-send-btn"
                aria-label={t('chat.aria_send_question')}
                disabled={!input.trim() || isLoadingHistory}
                id="chat-send-btn"
              >
                <Send size={15} />
              </button>
            )}
          </form>
          <p className="text-center text-xs text-faint mt-2">
            {t('chat.disclaimer')}
          </p>
        </div>
      </div>

      {/* PDF Viewer Pane */}
      {selectedPdfUrl && (
        <div 
          className="pdf-viewer-pane" 
          style={{ width: pdfPaneWidth, transition: isDraggingPdf ? 'none' : undefined }}
        >
          <div 
            className={`pdf-resize-handle ${isDraggingPdf ? 'active' : ''}`} 
            onMouseDown={handleMouseDownPdfResize} 
          />
          <div className="pdf-header">
            <span className="pdf-title" title={selectedPdfTitle}>{selectedPdfTitle}</span>
            <div className="pdf-actions">
              <button
                type="button"
                className="btn btn-ghost icon-button"
                aria-label={t('chat.btn_open_new')}
                onClick={() => {
                  window.open(selectedPdfUrl, '_blank', 'noopener,noreferrer');
                  setSelectedPdfUrl(null);
                }}
              >
                <ExternalLink size={16} />
              </button>
              <button
                type="button"
                className="btn btn-ghost icon-button"
                aria-label={t('chat.btn_close_doc')}
                onClick={() => setSelectedPdfUrl(null)}
              >
                <X size={16} />
              </button>
            </div>
          </div>
          <iframe
            key={selectedPdfUrl}
            src={selectedPdfUrl}
            className="pdf-iframe"
            title={t('chat.pdf_viewer_title')}
            style={{ pointerEvents: isDraggingPdf ? 'none' : 'auto' }}
          />
          {/* Invisible overlay to catch fast mouse movements over the iframe */}
          {isDraggingPdf && (
            <div style={{ position: 'fixed', inset: 0, zIndex: 9999, cursor: 'col-resize' }} />
          )}
        </div>
      )}
    </div>
  );
}
