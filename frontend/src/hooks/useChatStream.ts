import { useCallback, useEffect, useRef, useState } from 'react';
import { API_BASE_URL } from '../config';
import { useAuth } from '../context/auth';
import { extractSseEvents, getSseData } from '../utils/sse';
import { parseSources } from '../utils/validation';

export interface SourceNode {
  score: number;
  text: string;
  metadata: Record<string, unknown>;
}

export function useChatStream() {
  const [isStreaming, setIsStreaming] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);
  const { apiFetch } = useAuth();

  const cancelStream = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setIsStreaming(false);
  }, []);

  useEffect(() => cancelStream, [cancelStream]);

  const sendMessage = async (
    sessionId: string,
    message: string,
    onChunk: (chunk: string) => void,
    onSources: (sources: SourceNode[]) => void,
    onError: (message: string) => void
  ) => {
    cancelStream();
    const controller = new AbortController();
    controllerRef.current = controller;
    setIsStreaming(true);

    try {
      const endpoint = `${API_BASE_URL}/sessions/${sessionId}/chat`;

      const response = await apiFetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: message }),
        signal: controller.signal,
        retryOnAuth: false,
        timeoutMs: 3_600_000,
      });

      if (!response.ok) {
        throw new Error(`Chat request failed with status ${response.status}`);
      }
      if (!response.body) {
        throw new Error('ReadableStream is not supported');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let eventBuffer = '';
      let streamDone = false;

      const processEvent = (event: string) => {
        const dataStr = getSseData(event);
        if (!dataStr) return false;
        if (dataStr.trim() === '[DONE]') {
          streamDone = true;
          return false;
        }

        try {
          const data: unknown = JSON.parse(dataStr);
          if (!data || typeof data !== 'object') return false;
          if ('chunk' in data && typeof data.chunk === 'string') {
            onChunk(data.chunk);
            return true;
          } else if ('sources' in data) {
            onSources(parseSources(data.sources));
          } else if ('error' in data) {
            streamDone = true;
            onError('Máy chủ không thể hoàn tất câu trả lời.');
          }
        } catch (error) {
          console.warn('Ignored malformed SSE event', error);
        }
        return false;
      };

      while (!streamDone) {
        const { done, value } = await reader.read();
        eventBuffer += decoder.decode(value, { stream: !done });
        const extracted = extractSseEvents(eventBuffer);
        eventBuffer = extracted.remainder;
        for (let index = 0; index < extracted.events.length; index += 1) {
          const renderedChunk = processEvent(extracted.events[index]);
          if (renderedChunk && index < extracted.events.length - 1) {
            await new Promise<void>(resolve => window.requestAnimationFrame(() => resolve()));
          }
        }
        if (done) break;
      }

      if (!streamDone && eventBuffer.trim()) processEvent(eventBuffer);
    } catch (error) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) {
        console.error(error);
        onError('Không thể kết nối tới máy chủ.');
      }
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
        setIsStreaming(false);
      }
    }
  };

  return { sendMessage, isStreaming, cancelStream };
}
