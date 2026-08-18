import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { renderHook, waitFor, act } from '@testing-library/react';
import { AuthProvider } from '../src/auth/AuthContext';
import { DataProvider, useData } from '../src/data/DataContext';
import { DEMO_SPEAKERS } from '../src/data/demo';

function Providers({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <DataProvider>{children}</DataProvider>
    </AuthProvider>
  );
}

function speakersYaml(entries: unknown[]) {
  // Minimal hand-rolled YAML sequence, good enough for js-yaml to parse back.
  return entries.map(e => `- ${JSON.stringify(e)}`).join('\n');
}

describe('DataProvider (demo mode)', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    localStorage.setItem('convener.demo', '1');
  });

  it('loads the demo dataset without any network access', async () => {
    const { result } = renderHook(() => useData(), { wrapper: Providers });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.speakers).toHaveLength(DEMO_SPEAKERS.length);
    expect(result.current.config?.season).toBe(2026);
  });

  it('mutateSpeakers updates local state only, from current', async () => {
    const { result } = renderHook(() => useData(), { wrapper: Providers });
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.mutateSpeakers(
        current => current.map(s => ({ ...s, notes: 'edited' })),
        'edit',
      );
    });
    expect(result.current.speakers[0].notes).toBe('edited');
  });

  it('mutateConfig updates local state only, from current', async () => {
    const { result } = renderHook(() => useData(), { wrapper: Providers });
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.mutateConfig(current => ({ ...current, vote_threshold: 5 }), 'edit config');
    });
    expect(result.current.config?.vote_threshold).toBe(5);
  });

  it('useData throws when used outside a provider', () => {
    expect(() => renderHook(() => useData())).toThrow(/outside provider/);
  });
});

describe('DataProvider (real GitHub backend)', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    localStorage.setItem('convener.token', 'tok');
  });

  it('reload fetches speakers and config, decoding base64 content', async () => {
    const spkYaml = speakersYaml([{ id: 'a', status: 'lead', date: '', time: '' }]);
    const cfgYaml = 'season: 2026\nvw_counter: 1\nvote_threshold: 3\noverlap_window_days: 7\nseminar_duration_minutes: 90\nboard_members: []\n';
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.includes('/user')) {
          return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
        }
        if (url.includes('speakers.yml')) {
          return Promise.resolve({ ok: true, json: async () => ({ content: btoa(spkYaml), sha: 'spksha' }) });
        }
        return Promise.resolve({ ok: true, json: async () => ({ content: btoa(cfgYaml), sha: 'cfgsha' }) });
      }),
    );
    const { result } = renderHook(() => useData(), { wrapper: Providers });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.speakers).toHaveLength(1);
    expect(result.current.config?.vote_threshold).toBe(3);
    expect(result.current.error).toBeNull();
  });

  it('sets an error message when the fetch fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.includes('/user')) {
          return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
        }
        return Promise.resolve({ ok: false, status: 500, text: async () => 'boom' });
      }),
    );
    const { result } = renderHook(() => useData(), { wrapper: Providers });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toMatch(/GitHub 500/);
  });

  it('auto-sweeps a past scheduled talk to delivered and PUTs the update', async () => {
    const spkYaml = speakersYaml([
      { id: 'a', status: 'scheduled', date: '2000-01-01', time: '' },
    ]);
    const cfgYaml = 'season: 2026\nboard_members: []\n';
    let putBody: string | undefined;
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, opts?: RequestInit) => {
        if (url.includes('/user')) {
          return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
        }
        if (url.includes('speakers.yml') && opts?.method === 'PUT') {
          putBody = opts.body as string;
          return Promise.resolve({ ok: true, json: async () => ({ content: { sha: 'sweptsha' } }) });
        }
        if (url.includes('speakers.yml')) {
          return Promise.resolve({ ok: true, json: async () => ({ content: btoa(spkYaml), sha: 'spksha' }) });
        }
        return Promise.resolve({ ok: true, json: async () => ({ content: btoa(cfgYaml), sha: 'cfgsha' }) });
      }),
    );
    const { result } = renderHook(() => useData(), { wrapper: Providers });
    await waitFor(() => expect(result.current.loading).toBe(false));
    await waitFor(() => expect(result.current.spkSha).toBe('sweptsha'));
    expect(result.current.speakers[0].status).toBe('delivered');
    expect(putBody).toBeDefined();
    expect(JSON.parse(putBody!).message).toMatch(/auto-sweep/);
  });

  it('auto-sweeps a past scheduled talk with a set time to delivered', async () => {
    const spkYaml = speakersYaml([
      { id: 'a', status: 'scheduled', date: '2000-01-01', time: '12:30' },
    ]);
    const cfgYaml = 'season: 2026\nboard_members: []\n';
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, opts?: RequestInit) => {
        if (url.includes('/user')) {
          return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
        }
        if (url.includes('speakers.yml') && opts?.method === 'PUT') {
          return Promise.resolve({ ok: true, json: async () => ({ content: { sha: 'sweptsha' } }) });
        }
        if (url.includes('speakers.yml')) {
          return Promise.resolve({ ok: true, json: async () => ({ content: btoa(spkYaml), sha: 'spksha' }) });
        }
        return Promise.resolve({ ok: true, json: async () => ({ content: btoa(cfgYaml), sha: 'cfgsha' }) });
      }),
    );
    const { result } = renderHook(() => useData(), { wrapper: Providers });
    await waitFor(() => expect(result.current.loading).toBe(false));
    await waitFor(() => expect(result.current.speakers[0].status).toBe('delivered'));
  });

  it('does not sweep a scheduled talk with a set time that has not started yet', async () => {
    const farFuture = new Date(Date.now() + 365 * 86_400_000).toISOString().slice(0, 10);
    const spkYaml = speakersYaml([{ id: 'a', status: 'scheduled', date: farFuture, time: '12:30' }]);
    const cfgYaml = 'season: 2026\nboard_members: []\n';
    const putSpy = vi.fn();
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, opts?: RequestInit) => {
        if (url.includes('/user')) {
          return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
        }
        if (url.includes('speakers.yml') && opts?.method === 'PUT') {
          putSpy();
          return Promise.resolve({ ok: true, json: async () => ({ content: { sha: 'sweptsha' } }) });
        }
        if (url.includes('speakers.yml')) {
          return Promise.resolve({ ok: true, json: async () => ({ content: btoa(spkYaml), sha: 'spksha' }) });
        }
        return Promise.resolve({ ok: true, json: async () => ({ content: btoa(cfgYaml), sha: 'cfgsha' }) });
      }),
    );
    const { result } = renderHook(() => useData(), { wrapper: Providers });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.speakers[0].status).toBe('scheduled');
    expect(putSpy).not.toHaveBeenCalled();
  });

  it('mutateConfig PUTs the serialized config and updates the sha', async () => {
    const spkYaml = speakersYaml([{ id: 'a', status: 'lead', date: '', time: '' }]);
    const cfgYaml = 'season: 2026\nboard_members: []\n';
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, opts?: RequestInit) => {
        if (url.includes('/user')) {
          return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
        }
        if (url.includes('config.yml') && opts?.method === 'PUT') {
          return Promise.resolve({ ok: true, json: async () => ({ content: { sha: 'newcfgsha' } }) });
        }
        if (url.includes('speakers.yml')) {
          return Promise.resolve({ ok: true, json: async () => ({ content: btoa(spkYaml), sha: 'spksha' }) });
        }
        return Promise.resolve({ ok: true, json: async () => ({ content: btoa(cfgYaml), sha: 'cfgsha' }) });
      }),
    );
    const { result } = renderHook(() => useData(), { wrapper: Providers });
    await waitFor(() => expect(result.current.loading).toBe(false));
    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.mutateConfig(current => ({ ...current, vote_threshold: 7 }), 'msg');
    });
    expect(ok).toBe(true);
    expect(result.current.cfgSha).toBe('newcfgsha');
    expect(result.current.config?.vote_threshold).toBe(7);
  });

  it('mutateSpeakers PUTs the serialized YAML computed from current, and updates the sha', async () => {
    const spkYaml = speakersYaml([{ id: 'a', status: 'lead', date: '', time: '' }]);
    const cfgYaml = 'season: 2026\nboard_members: []\n';
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, opts?: RequestInit) => {
        if (url.includes('/user')) {
          return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
        }
        if (url.includes('speakers.yml') && opts?.method === 'PUT') {
          return Promise.resolve({ ok: true, json: async () => ({ content: { sha: 'newsha' } }) });
        }
        if (url.includes('speakers.yml')) {
          return Promise.resolve({ ok: true, json: async () => ({ content: btoa(spkYaml), sha: 'spksha' }) });
        }
        return Promise.resolve({ ok: true, json: async () => ({ content: btoa(cfgYaml), sha: 'cfgsha' }) });
      }),
    );
    const { result } = renderHook(() => useData(), { wrapper: Providers });
    await waitFor(() => expect(result.current.loading).toBe(false));
    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.mutateSpeakers(
        current => current.map(s => ({ ...s, notes: 'changed' })),
        'msg',
      );
    });
    expect(ok).toBe(true);
    expect(result.current.spkSha).toBe('newsha');
    expect(result.current.speakers[0].notes).toBe('changed');
  });

  it('mutateSpeakers surfaces a ConflictError through `error` instead of an unhandled rejection', async () => {
    const spkYaml = speakersYaml([{ id: 'a', status: 'lead', date: '', time: '' }]);
    const cfgYaml = 'season: 2026\nboard_members: []\n';
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, opts?: RequestInit) => {
        if (url.includes('/user')) {
          return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
        }
        // Every PUT is rejected as stale, like a sha the caller never wins.
        if (url.includes('speakers.yml') && opts?.method === 'PUT') {
          return Promise.resolve({ ok: false, status: 409, text: async () => 'stale sha' });
        }
        if (url.includes('speakers.yml')) {
          return Promise.resolve({ ok: true, json: async () => ({ content: btoa(spkYaml), sha: 'spksha' }) });
        }
        return Promise.resolve({ ok: true, json: async () => ({ content: btoa(cfgYaml), sha: 'cfgsha' }) });
      }),
    );
    const { result } = renderHook(() => useData(), { wrapper: Providers });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeNull();

    // Must not throw / reject unhandled — the whole point of the fix.
    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.mutateSpeakers(
        current => current.map(s => ({ ...s, notes: 'will never land' })),
        'msg',
      );
    });

    expect(ok).toBe(false);
    expect(result.current.error).toMatch(/someone else is editing/);
  });

  it('mutateConfig surfaces a ConflictError through `error` instead of an unhandled rejection', async () => {
    const spkYaml = speakersYaml([{ id: 'a', status: 'lead', date: '', time: '' }]);
    const cfgYaml = 'season: 2026\nboard_members: []\n';
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, opts?: RequestInit) => {
        if (url.includes('/user')) {
          return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
        }
        if (url.includes('config.yml') && opts?.method === 'PUT') {
          return Promise.resolve({ ok: false, status: 409, text: async () => 'stale sha' });
        }
        if (url.includes('speakers.yml')) {
          return Promise.resolve({ ok: true, json: async () => ({ content: btoa(spkYaml), sha: 'spksha' }) });
        }
        return Promise.resolve({ ok: true, json: async () => ({ content: btoa(cfgYaml), sha: 'cfgsha' }) });
      }),
    );
    const { result } = renderHook(() => useData(), { wrapper: Providers });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeNull();

    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.mutateConfig(current => ({ ...current, vote_threshold: 9 }), 'msg');
    });

    expect(ok).toBe(false);
    expect(result.current.error).toMatch(/someone else is editing/);
  });
});
