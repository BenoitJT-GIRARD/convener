import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { renderHook, waitFor, act } from '@testing-library/react';
import { AuthProvider } from '../src/auth/AuthContext';
import { DataProvider, useData } from '../src/data/DataContext';
import { demoSpeakers } from '../src/data/demo';
import { configYaml, speakersYaml } from './data-doubles';
import { dataEdit, identifier } from '../src/state/decisions';

/** These tests are about the write plumbing -- what is PUT, which sha comes
 *  back, how a conflict surfaces -- and not about what the subject says. It
 *  is a real one all the same: `mutateSpeakers`/`mutateConfig` take a
 *  `Subject`, so there is no string to pass here either. */
const SUBJECT = dataEdit(identifier('spk-001'), { part: 'admin-fields' });

function Providers({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <DataProvider>{children}</DataProvider>
    </AuthProvider>
  );
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
    expect(result.current.speakers).toHaveLength(demoSpeakers().length);
    expect(result.current.config?.season).toBe(2026);
  });

  it('mutateSpeakers updates local state only, from current', async () => {
    const { result } = renderHook(() => useData(), { wrapper: Providers });
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.mutateSpeakers(
        current => current.map(s => ({ ...s, notes: 'edited' })),
        SUBJECT,
      );
    });
    expect(result.current.speakers[0].notes).toBe('edited');
  });

  it('mutateConfig updates local state only, from current', async () => {
    const { result } = renderHook(() => useData(), { wrapper: Providers });
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.mutateConfig(current => ({ ...current, next_edition_number: 5 }), SUBJECT);
    });
    expect(result.current.config?.next_edition_number).toBe(5);
  });

  it('useData throws when used outside a provider', () => {
    expect(() => renderHook(() => useData())).toThrow(/outside provider/);
  });

  it('reload() in demo mode resets to the demo dataset without network access', async () => {
    const { result } = renderHook(() => useData(), { wrapper: Providers });
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.mutateSpeakers(current => current.map(s => ({ ...s, notes: 'x' })), SUBJECT);
    });
    expect(result.current.speakers[0].notes).toBe('x');
    await act(async () => {
      await result.current.reload();
    });
    expect(result.current.speakers[0].notes).not.toBe('x');
    expect(result.current.loading).toBe(false);
  });
});

describe('DataProvider (no session)', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('reload/mutateSpeakers/mutateConfig no-op without a token', async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    const { result } = renderHook(() => useData(), { wrapper: Providers });
    await act(async () => {
      await result.current.reload();
    });
    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.mutateSpeakers(current => current, SUBJECT);
    });
    expect(ok).toBe(false);
    await act(async () => {
      ok = await result.current.mutateConfig(current => current, SUBJECT);
    });
    expect(ok).toBe(false);
    expect(fetchSpy).not.toHaveBeenCalled();
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
    const cfgYaml = configYaml({ vote_window_days: 21 });
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
    expect(result.current.config?.vote_window_days).toBe(21);
    expect(result.current.error).toBeNull();
  });

  it('refuses to load rather than invent a config when config.yml is empty', async () => {
    // There used to be a constant default here, and an empty config.yml
    // loaded silently into it: the Board screen then showed a vote
    // threshold computed from a board nobody had elected. A repository
    // whose config cannot be read is an operator problem, and it says so.
    const spkYaml = speakersYaml([{ id: 'a', status: 'lead' }]);
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.includes('/user')) {
          return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
        }
        if (url.includes('speakers.yml')) {
          return Promise.resolve({ ok: true, json: async () => ({ content: btoa(spkYaml), sha: 'spksha' }) });
        }
        return Promise.resolve({ ok: true, json: async () => ({ content: btoa(''), sha: 'cfgsha' }) });
      }),
    );
    const { result } = renderHook(() => useData(), { wrapper: Providers });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.config).toBeNull();
    expect(result.current.error).toContain('instance/data/config.yml');
    expect(result.current.error).not.toMatch(/GitHub is not responding/);
  });

  it('names the file and the setting when config.yml carries one this app dropped', async () => {
    // The `vote_threshold` case: a setting the governance rule (G-01)
    // replaced, still sitting in the file, reading to whoever opens it as
    // though it still governs the vote.
    const spkYaml = speakersYaml([{ id: 'a', status: 'lead' }]);
    const cfgYaml = configYaml() + 'vote_threshold: 3\n';
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
    expect(result.current.error).toContain('vote_threshold');
    expect(result.current.error).toContain('instance/data/config.yml');
    expect(result.current.config).toBeNull();
  });

  it('sets a plain-language error message when the fetch fails, not the raw status/body', async () => {
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
    expect(result.current.error).toMatch(/GitHub is not responding/);
    expect(result.current.error).not.toMatch(/500|boom/);
  });

  it('never PUTs on load, even when a scheduled talk is long past its end time', async () => {
    const spkYaml = speakersYaml([
      { id: 'a', status: 'scheduled', date: '2000-01-01', time: '' },
    ]);
    const cfgYaml = configYaml();
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
    // The raw record is untouched: writing the transition is the scheduled
    // job's business (tools/convener_ops/maintenance/sweep.py), not the browser's.
    expect(result.current.speakers[0].status).toBe('scheduled');
    expect(result.current.spkSha).toBe('spksha');
    expect(putSpy).not.toHaveBeenCalled();
  });

  it('never PUTs on load for a scheduled talk with a set time that has already ended', async () => {
    const spkYaml = speakersYaml([
      { id: 'a', status: 'scheduled', date: '2000-01-01', time: '12:30' },
    ]);
    const cfgYaml = configYaml();
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

  it('does not sweep a scheduled talk with a set time that has not started yet', async () => {
    const farFuture = new Date(Date.now() + 365 * 86_400_000).toISOString().slice(0, 10);
    const spkYaml = speakersYaml([{ id: 'a', status: 'scheduled', date: farFuture, time: '12:30' }]);
    const cfgYaml = configYaml();
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
    const cfgYaml = configYaml();
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
      ok = await result.current.mutateConfig(current => ({ ...current, next_edition_number: 7 }), SUBJECT);
    });
    expect(ok).toBe(true);
    expect(result.current.cfgSha).toBe('newcfgsha');
    expect(result.current.config?.next_edition_number).toBe(7);
  });

  it('mutateSpeakers PUTs the serialized YAML computed from current, and updates the sha', async () => {
    const spkYaml = speakersYaml([{ id: 'a', status: 'lead', date: '', time: '' }]);
    const cfgYaml = configYaml();
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
        SUBJECT,
      );
    });
    expect(ok).toBe(true);
    expect(result.current.spkSha).toBe('newsha');
    expect(result.current.speakers[0].notes).toBe('changed');
  });

  it('mutateSpeakers surfaces a ConflictError through `saveError` instead of an unhandled rejection', async () => {
    const spkYaml = speakersYaml([{ id: 'a', status: 'lead', date: '', time: '' }]);
    const cfgYaml = configYaml();
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
    expect(result.current.saveError).toBeNull();

    // Must not throw / reject unhandled — the whole point of the fix.
    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.mutateSpeakers(
        current => current.map(s => ({ ...s, notes: 'will never land' })),
        SUBJECT,
      );
    });

    expect(ok).toBe(false);
    expect(result.current.saveError).toMatch(/someone else is editing/);
    // A save failure never destroys existing data or the load-error state.
    expect(result.current.error).toBeNull();
    expect(result.current.speakers[0].notes).not.toBe('will never land');
  });

  it('reload() re-fetches from GitHub without writing anything', async () => {
    const spkYaml = speakersYaml([{ id: 'a', status: 'lead', date: '', time: '' }]);
    const cfgYaml = configYaml();
    const putSpy = vi.fn();
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, opts?: RequestInit) => {
        if (url.includes('/user')) {
          return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
        }
        if (opts?.method === 'PUT') {
          putSpy();
          return Promise.resolve({ ok: true, json: async () => ({ content: { sha: 'x' } }) });
        }
        if (url.includes('speakers.yml')) {
          return Promise.resolve({ ok: true, json: async () => ({ content: btoa(spkYaml), sha: 'spksha2' }) });
        }
        return Promise.resolve({ ok: true, json: async () => ({ content: btoa(cfgYaml), sha: 'cfgsha2' }) });
      }),
    );
    const { result } = renderHook(() => useData(), { wrapper: Providers });
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.reload();
    });
    expect(result.current.spkSha).toBe('spksha2');
    expect(result.current.error).toBeNull();
    expect(putSpy).not.toHaveBeenCalled();
  });

  it('reload() surfaces a fetch failure through `error`', async () => {
    const spkYaml = speakersYaml([{ id: 'a', status: 'lead', date: '', time: '' }]);
    const cfgYaml = configYaml();
    let fail = false;
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.includes('/user')) {
          return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
        }
        if (fail) {
          return Promise.resolve({ ok: false, status: 500, text: async () => 'boom' });
        }
        if (url.includes('speakers.yml')) {
          return Promise.resolve({ ok: true, json: async () => ({ content: btoa(spkYaml), sha: 'spksha' }) });
        }
        return Promise.resolve({ ok: true, json: async () => ({ content: btoa(cfgYaml), sha: 'cfgsha' }) });
      }),
    );
    const { result } = renderHook(() => useData(), { wrapper: Providers });
    await waitFor(() => expect(result.current.loading).toBe(false));
    fail = true;
    await act(async () => {
      await result.current.reload();
    });
    expect(result.current.error).toMatch(/GitHub is not responding/);
    expect(result.current.error).not.toMatch(/500|boom/);
  });

  it('stays loading while a stored credential is still being validated, and never reports an empty result before the data arrives', async () => {
    const spkYaml = speakersYaml([{ id: 'a', status: 'lead', date: '', time: '' }]);
    const cfgYaml = configYaml();

    // The /user validation call (triggered by AuthContext re-checking the
    // stored legacy token) is held open until the test explicitly resolves
    // it, to simulate the network round trip a real validation takes.
    let resolveUser: () => void = () => {};
    const userGate = new Promise<void>(resolve => {
      resolveUser = resolve;
    });

    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.includes('/user')) {
          return userGate.then(() => ({ ok: true, json: async () => ({ login: 'alice' }) }));
        }
        if (url.includes('speakers.yml')) {
          return Promise.resolve({ ok: true, json: async () => ({ content: btoa(spkYaml), sha: 'spksha' }) });
        }
        return Promise.resolve({ ok: true, json: async () => ({ content: btoa(cfgYaml), sha: 'cfgsha' }) });
      }),
    );

    const { result } = renderHook(() => useData(), { wrapper: Providers });

    // Auth hasn't resolved yet: must stay loading, and must not have
    // concluded "signed out, nothing to load".
    expect(result.current.loading).toBe(true);
    expect(result.current.speakers).toHaveLength(0);

    // Let pending microtasks run without resolving the /user call -- still
    // must not report a confident empty state.
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current.loading).toBe(true);
    expect(result.current.speakers).toHaveLength(0);

    await act(async () => {
      resolveUser();
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.speakers).toHaveLength(1);
  });

  it('mutateConfig surfaces a ConflictError through `saveError` instead of an unhandled rejection', async () => {
    const spkYaml = speakersYaml([{ id: 'a', status: 'lead', date: '', time: '' }]);
    const cfgYaml = configYaml();
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
      ok = await result.current.mutateConfig(current => ({ ...current, next_edition_number: 9 }), SUBJECT);
    });

    expect(ok).toBe(false);
    expect(result.current.saveError).toMatch(/someone else is editing/);
    expect(result.current.error).toBeNull();
  });

  it('clearSaveError dismisses the save-error banner without touching anything else', async () => {
    const spkYaml = speakersYaml([{ id: 'a', status: 'lead', date: '', time: '' }]);
    const cfgYaml = configYaml();
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
    await act(async () => {
      await result.current.mutateConfig(current => ({ ...current, next_edition_number: 9 }), SUBJECT);
    });
    expect(result.current.saveError).not.toBeNull();
    act(() => result.current.clearSaveError());
    expect(result.current.saveError).toBeNull();
  });
});
