import { describe, expect, it } from 'vitest';
import { parseMessages, parseSessions, parseSources, parseUser } from './validation';

describe('API response validation', () => {
  it('accepts valid auth and chat payloads', () => {
    expect(parseUser({ id: 1, username: 'admin', role: 'admin' })).toEqual({
      id: 1,
      username: 'admin',
      role: 'admin',
    });
    expect(parseMessages([{
      id: '1',
      role: 'assistant',
      content: 'answer',
      sources: [{ score: 0.9, text: 'law', metadata: { file_name: 'law.pdf' } }],
    }])).toHaveLength(1);
  });

  it('rejects malformed top-level payloads and filters malformed sources', () => {
    expect(() => parseSessions({ id: 'not-an-array' })).toThrow();
    expect(() => parseMessages([{ role: 'assistant' }])).toThrow();
    expect(parseSources([{ score: 'bad' }, null])).toEqual([]);
  });
});
