import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { useRole } from '../src/auth/useRole';
import { AuthProvider } from '../src/auth/AuthContext';
import { DataProvider } from '../src/data/DataContext';

function Providers({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <DataProvider>{children}</DataProvider>
    </AuthProvider>
  );
}

describe('useRole', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('returns null when there is no session', () => {
    const { result } = renderHook(() => useRole(), { wrapper: Providers });
    expect(result.current).toBeNull();
  });

  it('returns board immediately in demo mode', async () => {
    localStorage.setItem('convener.demo', '1');
    const { result } = renderHook(() => useRole(), { wrapper: Providers });
    await waitFor(() => expect(result.current).toBe('board'));
  });

  it('resolves the role from detectRole once signed in', async () => {
    localStorage.setItem('convener.token', 'tok');
    const b64 = btoa('season: 2026\n');
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.includes('/user')) {
          return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
        }
        if (url.includes('/teams/')) {
          return Promise.resolve({ ok: true, json: async () => ({ state: 'active' }) });
        }
        // config/speakers file fetches from DataProvider's reload()
        return Promise.resolve({ ok: true, json: async () => ({ content: b64, sha: 's' }) });
      }),
    );
    const { result } = renderHook(() => useRole(), { wrapper: Providers });
    await waitFor(() => expect(result.current).toBe('board'));
  });
});
