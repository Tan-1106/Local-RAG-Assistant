import { useState } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider } from './AuthContext';
import { useAuth } from './auth';

const user = { id: 1, username: 'admin', role: 'admin' };

function jsonResponse(status: number, body: unknown, csrf = false) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json',
      ...(csrf ? { 'X-CSRF-Token': 'csrf-token' } : {}),
    },
  });
}

function Probe({ method }: { method: 'GET' | 'POST' }) {
  const { user: currentUser, apiFetch } = useAuth();
  const [status, setStatus] = useState('');
  return (
    <>
      <span>{currentUser?.username ?? 'anonymous'}</span>
      <button
        onClick={() => void apiFetch('/api/resource', { method }).then(response => {
          setStatus(String(response.status));
        })}
      >
        request
      </button>
      <span data-testid="status">{status}</span>
    </>
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('AuthProvider request retry policy', () => {
  it('refreshes and retries a safe GET request once', async () => {
    let meCalls = 0;
    let resourceCalls = 0;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/auth/me')) {
        meCalls += 1;
        return meCalls === 1
          ? jsonResponse(200, user, true)
          : jsonResponse(401, {});
      }
      if (url.endsWith('/auth/refresh')) return jsonResponse(200, user, true);
      resourceCalls += 1;
      return resourceCalls === 1
        ? jsonResponse(401, {})
        : jsonResponse(200, { ok: true });
    }));

    render(<AuthProvider><Probe method="GET" /></AuthProvider>);
    await screen.findByText('admin');
    fireEvent.click(screen.getByRole('button', { name: 'request' }));

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('200'));
    expect(resourceCalls).toBe(2);
  });

  it('refreshes but never replays an unsafe POST request', async () => {
    let meCalls = 0;
    let resourceCalls = 0;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/auth/me')) {
        meCalls += 1;
        return meCalls === 1
          ? jsonResponse(200, user, true)
          : jsonResponse(401, {});
      }
      if (url.endsWith('/auth/refresh')) return jsonResponse(200, user, true);
      resourceCalls += 1;
      return jsonResponse(401, {});
    }));

    render(<AuthProvider><Probe method="POST" /></AuthProvider>);
    await screen.findByText('admin');
    fireEvent.click(screen.getByRole('button', { name: 'request' }));

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('401'));
    expect(resourceCalls).toBe(1);
  });
});
