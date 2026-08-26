import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { useAuth } from '../auth/AuthContext';
import { getFile, githubStore } from '../github/contents';
import { mutate } from '../github/mutate';
import { friendlyError } from '../github/errors';
import {
  parseSpeakers,
  serializeSpeakers,
  parseConfig,
  serializeConfig,
  withSpeakersHeader,
  withConfigHeader,
} from './yaml';
import { isDemoMode, demoSpeakers, demoConfig } from './demo';
import type { Speaker, Config } from './types';
import type { Subject } from '../state/decisions';

interface State {
  loading: boolean;
  /** Set only when the *initial load* (or an explicit reload) fails. There is
   *  genuinely nothing to render in that case, so screens replace themselves
   *  with this — see `error` usage in the screens under src/screens. */
  error: string | null;
  /** Set only when a *write* fails. Unlike `error`, existing data is never
   *  cleared for this — screens must show it as a dismissible banner and
   *  leave the user's work on screen, never replace the page with it. */
  saveError: string | null;
  speakers: Speaker[];
  config: Config | null;
  spkSha: string;
  cfgSha: string;
}

interface Ctx extends State {
  reload: () => Promise<void>;
  /** Resolves `true` if the write went through, `false` if it was caught and
   *  surfaced via `saveError` — callers whose code after the write has a
   *  user-visible success side effect (a confirmation, a navigation) must
   *  guard it on this, so a failed write never reports success. */
  /** `message` may be a function of the list about to be written, for a
   *  subject that names something the transformation assigned -- the id of a
   *  record just created. It is called once, on the value that actually goes
   *  to GitHub.
   *
   *  It is a `Subject`, not a `string`: a commit subject is permanent and
   *  unrewritable, and `state/decisions.ts` is where the two forms one can
   *  take are assembled. Anything else -- a template literal here, a
   *  concatenation, a helper of its own -- fails to compile rather than
   *  being noticed later by a source walk that has to guess how the defect
   *  was spelled. */
  mutateSpeakers: (
    transform: (current: Speaker[]) => Speaker[],
    message: Subject | ((next: Speaker[]) => Subject),
  ) => Promise<boolean>;
  mutateConfig: (
    transform: (current: Config) => Config,
    message: Subject,
  ) => Promise<boolean>;
  /** Dismiss the current save-error banner without touching anything else. */
  clearSaveError: () => void;
}

const C = createContext<Ctx | null>(null);

/** The example instance, as this context's own state.
 *
 *  A function rather than a constant: the two
 *  documents behind it are parsed on first use rather than at module load
 *  (see `./demo.ts`), and a fresh copy per call is what lets `reload()`
 *  put back what an edit in this tab changed. */
function demoState(): State {
  return {
    loading: false,
    error: null,
    saveError: null,
    speakers: [...demoSpeakers()],
    config: { ...demoConfig() },
    spkSha: 'demo',
    cfgSha: 'demo',
  };
}

/** The synchronous half of loading: demo mode resolves immediately (no
 *  network), and having no token yet has nothing to load. Only the real
 *  GitHub read is genuinely asynchronous, so it's the only part that runs
 *  from inside the effect below. */
function initialState(token: string | null): State {
  if (isDemoMode()) return demoState();
  return {
    loading: !!token,
    error: null,
    saveError: null,
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
  const config = parseConfig(cfg.text);
  return {
    loading: false,
    error: null,
    saveError: null,
    speakers,
    config,
    spkSha: spk.sha,
    cfgSha: cfg.sha,
  };
}

export function DataProvider({ children }: { children: ReactNode }) {
  const { token, ready } = useAuth();
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
    // Nothing to fetch yet (auth still resolving a stored credential) or
    // ever (no session): `visible` below already reflects both cases
    // without needing a render just to push that through state.
    if (isDemoMode() || !ready || !token) return;
    let cancelled = false;
    fetchState(token)
      .then(next => {
        if (!cancelled) setS(next);
      })
      .catch(e => {
        if (!cancelled) {
          setS(p => ({ ...p, loading: false, error: friendlyError(e, 'load') }));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token, ready]);

  // The state exposed to consumers. While auth hasn't resolved (`ready` is
  // false -- a stored legacy or refresh token is still validating), whether
  // there will turn out to be a token is unknown, so this stays loading
  // rather than reporting "signed out, nothing to load". Once `ready` is
  // true, a missing token genuinely does mean there is nothing to fetch.
  // Both cases are fully determined by `ready`/`token` and computed here at
  // render time -- no extra setState, no extra render.
  const visible: State =
    isDemoMode() || (ready && token)
      ? s
      : !ready
        ? { ...s, loading: true }
        : {
            ...s,
            loading: false,
            speakers: [],
            config: null,
            spkSha: '',
            cfgSha: '',
          };

  async function reload() {
    if (!token) return;
    if (isDemoMode()) {
      setS(demoState());
      return;
    }
    setS(p => ({ ...p, loading: true, error: null }));
    try {
      setS(await fetchState(token));
    } catch (e) {
      setS(p => ({ ...p, loading: false, error: friendlyError(e, 'load') }));
    }
  }

  async function mutateSpeakers(
    transform: (current: Speaker[]) => Speaker[],
    message: Subject | ((next: Speaker[]) => Subject),
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
      setS(p => ({ ...p, speakers: result.value, spkSha: result.sha, saveError: null }));
      return true;
    } catch (e) {
      setS(p => ({ ...p, saveError: friendlyError(e, 'save') }));
      return false;
    }
  }

  async function mutateConfig(
    transform: (current: Config) => Config,
    message: Subject,
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
        parse: parseConfig,
        serialize: v => withConfigHeader(serializeConfig(v)),
        transform,
        message,
      });
      setS(p => ({ ...p, config: result.value, cfgSha: result.sha, saveError: null }));
      return true;
    } catch (e) {
      setS(p => ({ ...p, saveError: friendlyError(e, 'save') }));
      return false;
    }
  }

  function clearSaveError() {
    setS(p => ({ ...p, saveError: null }));
  }

  return (
    <C.Provider value={{ ...visible, reload, mutateSpeakers, mutateConfig, clearSaveError }}>
      {children}
    </C.Provider>
  );
}

export function useData() {
  const c = useContext(C);
  if (!c) throw new Error('useData outside provider');
  return c;
}
