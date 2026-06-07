import type { User } from '../context/auth';
import type { SourceNode } from '../hooks/useChatStream';

export interface ApiMessage {
  id: string | number;
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceNode[];
}

export interface ApiSession {
  id: string;
  title: string;
  created_at: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function parseUser(value: unknown): User {
  if (
    !isRecord(value)
    || typeof value.id !== 'number'
    || typeof value.username !== 'string'
    || typeof value.role !== 'string'
  ) {
    throw new Error('Invalid user response');
  }
  return { id: value.id, username: value.username, role: value.role };
}

export function parseSessions(value: unknown): ApiSession[] {
  if (!Array.isArray(value)) throw new Error('Invalid sessions response');
  return value.map(item => {
    if (
      !isRecord(item)
      || typeof item.id !== 'string'
      || typeof item.title !== 'string'
      || typeof item.created_at !== 'string'
    ) {
      throw new Error('Invalid session response');
    }
    return { id: item.id, title: item.title, created_at: item.created_at };
  });
}

export function parseSources(value: unknown): SourceNode[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap(item => {
    if (
      !isRecord(item)
      || typeof item.score !== 'number'
      || typeof item.text !== 'string'
      || !isRecord(item.metadata)
    ) {
      return [];
    }
    return [{
      score: item.score,
      text: item.text,
      metadata: item.metadata,
    }];
  });
}

export function parseMessages(value: unknown): ApiMessage[] {
  if (!Array.isArray(value)) throw new Error('Invalid messages response');
  return value.map(item => {
    if (
      !isRecord(item)
      || (typeof item.id !== 'string' && typeof item.id !== 'number')
      || (item.role !== 'user' && item.role !== 'assistant')
      || typeof item.content !== 'string'
    ) {
      throw new Error('Invalid message response');
    }
    return {
      id: item.id,
      role: item.role,
      content: item.content,
      sources: parseSources(item.sources),
    };
  });
}
