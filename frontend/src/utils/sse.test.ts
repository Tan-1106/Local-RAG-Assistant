import { describe, expect, it } from 'vitest';
import { extractSseEvents, getSseData } from './sse';

describe('SSE parsing', () => {
  it('keeps incomplete events for the next network chunk', () => {
    const first = extractSseEvents('data: {"chunk":"xin');
    expect(first.events).toEqual([]);

    const second = extractSseEvents(`${first.remainder} chào"}\n\ndata: [DO`);
    expect(second.events).toEqual(['data: {"chunk":"xin chào"}']);
    expect(second.remainder).toBe('data: [DO');

    const third = extractSseEvents(`${second.remainder}NE]\n\n`);
    expect(third.events).toEqual(['data: [DONE]']);
    expect(third.remainder).toBe('');
  });

  it('supports CRLF and multi-line data fields', () => {
    const result = extractSseEvents('data: line one\r\ndata: line two\r\n\r\n');
    expect(getSseData(result.events[0])).toBe('line one\nline two');
  });
});
