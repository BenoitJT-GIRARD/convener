import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { useAuth } from '../auth/AuthContext';
import { getFile, githubStore } from '../github/contents';
import { mutate } from '../github/mutate';
import {
  parseSpeakers,
  serializeSpeakers,
  parseConfig,
  serializeConfig,
  withSpeakersHeader,
  withConfigHeader,
} from './yaml';
import { isDemoMode, DEMO_SPEAKERS, DEMO_CONFIG } from './demo';
import type { Speaker, Config } from './types';

interface State {
  loading: boolean;
  error: string | null;
  speakers: Speaker[];
  config: Config | null;
  spkSha: string;
  cfgSha: string;
}

interface Ctx extends State {
  reload: () => Promise<void>;
  /** Resolves `true` if the write went through, `false` if it was caught and
   *  surfaced via `error` — callers whose code after the write has a
   *  user-visible success side effect (a confirmation, a navigation) must
   *  guard it on this, so a failed write never reports success. */
  mutateSpeakers: (
    transform: (current: Speaker[]) => Speaker[],
    message: string,
  ) => Promise<boolean>;
  mutateConfig: (
    transform: (current: Config) => Config,
    message: string,
  ) => Promise<boolean>;
}

const C = createContext<Ctx | null>(null);

const DEFAULT_CONFIG: Config = {
  season: 2026,
  vw_counter: 1,
  vote_threshold: 3,
  overlap_window_days: 7,
  seminar_duration_minutes: 90,
  board_members: [],
};

const DEMO_STATE: State = {
  loading: false,
  error: null,
  speakers: [...DEMO_SPEAKERS],
  config: { ...DEMO_CONFIG },
  spkSha: 'demo',
  cfgSha: 'demo',
};

/** The synchronous half of loading: demo mode resolves immediately (no
 *  network), and having no token yet has nothing to load. Only the real
 *  GitHub read is genuinely asynchronous, so it's the only part that runs
 *  from inside the effect below. */
function initialState(token: string | null): State {
  if (isDemoMode()) return DEMO_STATE;
  return {
    loading: !!token,
    error: null,
    speakers: [],
    config: null,
    spkSha: '',
    cfgSha: '',
  };
}

/** Read-only: fetch speakers and config from GitHub. Never writes — the
 *  scheduled->delivered transition is derived for display (see
 *  src/state/derived.ts) and persisted only by the scheduled job, so two
 *  volunteers opening the app at once can never race on the same write. */
async function fetchState(token: string): Promise<State> {
  const [spk, cfg] = await Promise.all([
    getFile('data/speakers.yml', token),
    getFile('data/config.yml', token),
  ]);
  const speakers = parseSpeakers(spk.text);
  const config = parseConfig(cfg.text) ?? DEFAULT_CONFIG;
  return {
    loading: false,
    error: null,
    speakers,
    config,
    spkSha: spk.sha,
    cfgSha: cfg.sha,
  };
}

export function DataProvider({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  // The synchronous half of loading (demo mode, or no token yet) is resolved
  // directly in the initialiser, keyed off the token this component mounted
  // with — `Shell` only renders `DataProvider` once a token exists, and
  // swaps it out for `<Login/>` rather than mounting it with a null token,
  // so `token` is stable for the lifetime of this component. Only the
  // genuinely asynchronous GitHub read runs from inside the effect below,
  // and it sets state solely from its promise callbacks — never
  // synchronously in the effect body — so there is nothing here for
  // react-hooks/set-state-in-effect to flag.
  const [s, setS] = useState<State>(() => initialState(token));

  useEffect(() => {
    if (isDemoMode() || !token) return;
    let cancelled = false;
    fetchState(token)
      .then(next => {
        if (!cancelled) setS(next);
      })
      .catch(e => {
        if (!cancelled) {
          const message = e instanceof Error ? e.message : String(e);
          setS(p => ({ ...p, loading: false, error: message }));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function reload() {
    if (!token) return;
    if (isDemoMode()) {
      setS(DEMO_STATE);
      return;
    }
    setS(p => ({ ...p, loading: true, error: null }));
    try {
      setS(await fetchState(token));
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setS(p => ({ ...p, loading: false, error: message }));
    }
  }

  async function mutateSpeakers(
    transform: (current: Speaker[]) => Speaker[],
    message: string,
  ): Promise<boolean> {
    if (!token) return false;
    if (isDemoMode()) {
      setS(p => ({ ...p, speakers: transform(p.speakers) }));
      return true;
    }
    try {
      const result = await mutate({
        store: githubStore(token),
        path: 'data/speakers.yml',
        parse: parseSpeakers,
        serialize: v => withSpeakersHeader(serializeSpeakers(v)),
        transform,
        message,
      });
      setS(p => ({ ...p, speakers: result.value, spkSha: result.sha }));
      return true;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setS(p => ({ ...p, error: msg }));
      return false;
    }
  }

  async function mutateConfig(
    transform: (current: Config) => Config,
    message: string,
  ): Promise<boolean> {
    if (!token) return false;
    if (isDemoMode()) {
      setS(p => ({ ...p, config: p.config ? transform(p.config) : p.config }));
      return true;
    }
    try {
      const result = await mutate({
        store: githubStore(token),
        path: 'data/config.yml',
        parse: text => parseConfig(text) ?? DEFAULT_CONFIG,
        serialize: v => withConfigHeader(serializeConfig(v)),
        transform,
        message,
      });
      setS(p => ({ ...p, config: result.value, cfgSha: result.sha }));
      return true;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setS(p => ({ ...p, error: msg }));
      return false;
    }
  }

  return (
    <C.Provider value={{ ...s, reload, mutateSpeakers, mutateConfig }}>{children}</C.Provider>
  );
}

export function useData() {
  const c = useContext(C);
  if (!c) throw new Error('useData outside provider');
  return c;
}
