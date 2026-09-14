import { createContext, useContext, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useAuth } from '../auth/AuthContext';
import { configTextFor } from './config-write';
import { getFile, githubStore } from '../github/contents';
import { mutate } from '../github/mutate';
import { friendlyError } from '../github/errors';
import {
  parseSpeakers,
  serializeSpeakers,
  parseConfig,
  SPEAKERS_HEADER,
  underItsOwnHeader,
} from './yaml';
import { isDemoMode, demoSpeakers, demoConfig } from './demo';
import {
  applyPending,
  enqueue,
  pendingCount,
  pendingSubject,
  type Queue,
  type QueuedEdit,
} from './pending';
import { forgetDemoSession, readDemoSession, writeDemoSession } from './demo-session';
import { configFile, speakersFile } from '../paths';
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
  /** Hold an edit to one record rather than writing it now.
   *
   *  For the two forms of the checklist that record something already done
   *  elsewhere -- a box ticked, a detail typed -- and for nothing else. A
   *  transition goes through `mutateSpeakers`, which flushes this first.
   *
   *  `speakers` above already has whatever is held applied to it, so a caller
   *  reads the same list whether an edit has been written or not. */
  queueSpeakerEdit: (id: string, item: QueuedEdit) => Promise<void>;
  /** Write whatever is held, now. Called by the save control, by every
   *  transition, and on the way out of a record. Resolves `true` when there
   *  is nothing held or the write went through. */
  flushSpeakers: () => Promise<boolean>;
  /** How many edits are waiting, for the screen that has to say so. Zero
   *  means the record on screen is the record in the repository. */
  pendingEdits: number;
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

/** The demonstration as this tab has it: what somebody has already done to
 *  it, and the example instance for a tab that has done nothing yet.
 *
 *  Where a demonstration's edits live, and how long for, is
 *  `./demo-session.ts` -- the session and not a day longer, and the whole
 *  argument for that is in its own header. This context used to hold them
 *  in `useState` and nowhere else, so a reload, or following a link out to
 *  the showcase and back, put a visitor at the beginning again with no
 *  sign that anything had happened. */
function demoStateForThisTab(): State {
  const kept = readDemoSession();
  if (!kept) return demoState();
  return {
    loading: false,
    error: null,
    saveError: null,
    speakers: kept.speakers,
    config: kept.config,
    spkSha: 'demo',
    cfgSha: 'demo',
  };
}

/** The synchronous half of loading: demo mode resolves immediately (no
 *  network), and having no token yet has nothing to load. Only the real
 *  GitHub read is genuinely asynchronous, so it's the only part that runs
 *  from inside the effect below. */
function initialState(token: string | null): State {
  if (isDemoMode()) return demoStateForThisTab();
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
    getFile(speakersFile(), token),
    getFile(configFile(), token),
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
      // The example instance's own records, put back. `reload` is the one
      // gesture that means "show me what the repository holds", and in a
      // demonstration the repository is the example -- so this is also
      // where a visitor undoes the whole of what they have done.
      forgetDemoSession();
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

  // Held in a ref *and* in state, and both are needed. The ref is what the
  // asynchronous code below reads -- a closure capturing the state value
  // would flush whatever the queue was when the timer was set. The state is
  // what a render reads, so a ticked box stays ticked on screen the moment it
  // is clicked rather than a write later.
  const queueRef = useRef<Queue | null>(null);
  const [queue, setQueueState] = useState<Queue | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function setQueue(next: Queue | null) {
    queueRef.current = next;
    setQueueState(next);
  }

  /** Write one queue. Separate from `flushSpeakers` because `queueSpeakerEdit`
   *  has to be able to write the *previous* record's queue while keeping the
   *  new one it has just started. */
  async function writeQueue(toWrite: Queue): Promise<boolean> {
    return writeSpeakers(
      current => applyPending(toWrite, current),
      pendingSubject(toWrite),
    );
  }

  async function flushSpeakers(): Promise<boolean> {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    const held = queueRef.current;
    if (held === null || held.edits.length === 0) return true;
    // Cleared before the write, not after. A tick arriving while this is in
    // flight belongs to the *next* queue; leaving it here would write it
    // twice -- once in this batch and once in the next.
    setQueue(null);
    const wrote = await writeQueue(held);
    if (!wrote) {
      // Put it back. The banner says the write failed, and the volunteer's
      // work is still on screen and still held, which is the whole reason
      // `saveError` never clears the records.
      setQueue(queueRef.current === null ? held : { id: held.id, edits: [...held.edits, ...queueRef.current.edits] });
    }
    return wrote;
  }

  /** How long a queue waits before it writes itself.
   *
   *  **A net is not supposed to catch the ordinary case.** Every other way a
   *  queue empties is somebody doing something -- leaving the record,
   *  starting a transition, pressing the control, moving to another tab.
   *  This timer exists for the one case nobody performs: a record left open
   *  on a screen somebody has walked away from. If it fires during ordinary
   *  work then it is not a backstop, it is the mechanism -- and it will
   *  split a volunteer's work into commits at the rhythm of their pauses
   *  rather than the rhythm of their work.
   *
   *  Twenty minutes, because ten is still an ordinary pause. A volunteer
   *  ticks "posted on LinkedIn" after posting on LinkedIn, and reads the
   *  next line of the runbook before ticking that.
   *
   *  **The first number here was fitted to the wrong cadence** and is worth
   *  recording, because it is the trap: it came from the session that
   *  exhausted an instance's month -- median gap between commits 10
   *  seconds, lower quartile 4 -- which was the person who built the series
   *  walking a runbook he already knew, at the speed of somebody checking
   *  that it works. Nobody doing the work goes at that speed.
   *
   *  **What a window this long would have risked, and what closes it.** At
   *  two minutes the exposure was small enough to leave alone: an
   *  unattended tab, and `beforeunload` asks the browser to warn before a
   *  deliberate close. Twenty minutes is long enough that a browser may
   *  discard a backgrounded tab for memory in the meantime, or a laptop may
   *  sleep, and neither runs an unload handler you can rely on. So the
   *  queue is now also written when the page is *hidden* -- see the effect
   *  in `components/PendingEdits.tsx`. That is the moment a volunteer
   *  switches away to go and do the thing the line describes, which makes
   *  it both the safe moment and the right one: one commit per stretch of
   *  work on a record, rather than one per pause in it. */
  const QUEUE_MS = 1_200_000;

  async function queueSpeakerEdit(id: string, item: QueuedEdit): Promise<void> {
    if (!token) return;
    if (isDemoMode()) {
      // Nothing is committed in a demonstration, so there is nothing to
      // batch: the edit applies to the session copy straight away and the
      // visitor sees exactly what a volunteer would.
      await writeSpeakers(current => applyPending({ id, edits: [item] }, current), pendingSubject({ id, edits: [item] }));
      return;
    }
    const { queue: next, flush } = enqueue(queueRef.current, id, item);
    setQueue(next);
    if (timerRef.current !== null) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      void flushSpeakers();
    }, QUEUE_MS);
    // A different record: the one being held is written now rather than
    // merged, because a commit subject can only name one of them.
    if (flush !== null) await writeQueue(flush);
  }

  async function mutateSpeakers(
    transform: (current: Speaker[]) => Speaker[],
    message: Subject | ((next: Speaker[]) => Subject),
  ): Promise<boolean> {
    // Every transition passes through here, so this is where the queue is
    // emptied -- once, at the chokepoint, rather than at each of the call
    // sites that would have to remember. A status change publishes an
    // edition or sends somebody a message, and doing that on top of ticks
    // this tab has not written would record the two in the wrong order.
    //
    // Its own write, not folded into the transition's: a transition's subject
    // is a line of the decision register, and bookkeeping merged into it
    // would make that line describe two different things.
    if (!(await flushSpeakers())) return false;
    return writeSpeakers(transform, message);
  }

  async function writeSpeakers(
    transform: (current: Speaker[]) => Speaker[],
    message: Subject | ((next: Speaker[]) => Subject),
  ): Promise<boolean> {
    if (!token) return false;
    if (isDemoMode()) {
      setS(p => {
        const next = { ...p, speakers: transform(p.speakers) };
        writeDemoSession(next.speakers, next.config);
        return next;
      });
      return true;
    }
    try {
      const result = await mutate({
        store: githubStore(token),
        path: speakersFile(),
        parse: (text: string) => text,
        serialize: (text: string) => text,
        // Under the header the file already had, not under the constant. A
        // write used to replace sixty-seven lines of the example instance's
        // own explanation with one -- see `underItsOwnHeader`.
        transform: (text: string) =>
          underItsOwnHeader(
            text,
            serializeSpeakers(transform(parseSpeakers(text))),
            SPEAKERS_HEADER,
          ),
        // The subject may be a function of what is about to be written --
        // `NewSpeaker` names the id it assigned, which only the winning
        // attempt settles. It is handed the records, not the bytes: the
        // caller reasons about a list of speakers and should not have to
        // learn that this writer works in text.
        message:
          typeof message === 'function'
            ? (text: string) => message(parseSpeakers(text))
            : message,
      });
      setS(p => ({
        ...p,
        speakers: parseSpeakers(result.value),
        spkSha: result.sha,
        saveError: null,
      }));
      return true;
    } catch (e) {
      setS(p => ({ ...p, saveError: friendlyError(e, 'save') }));
      return false;
    }
  }

  // Held edits are applied to what every screen reads, so a box stays ticked
  // the moment it is clicked. It is `applyPending` doing it -- the same
  // function the write transforms with -- so what is on screen and what will
  // land cannot be two different answers.
  const onScreen: State = { ...visible, speakers: applyPending(queue, visible.speakers) };

  async function mutateConfig(
    transform: (current: Config) => Config,
    message: Subject,
  ): Promise<boolean> {
    if (!token) return false;
    if (isDemoMode()) {
      setS(p => {
        const next = { ...p, config: p.config ? transform(p.config) : p.config };
        writeDemoSession(next.speakers, next.config);
        return next;
      });
      return true;
    }
    try {
      // Text in, text out. The transform still works on the parsed `Config`,
      // because that is what every caller reasons about -- but what reaches
      // the API is the original file with only the blocks that changed
      // rewritten. A parse-and-serialise here used to replace the file's own
      // header with a constant and drop every comment in it: thirty lines of
      // an instance's own reasoning, deleted by a write that moved one
      // integer. See `data/config-write.ts` for the measurement.
      const result = await mutate({
        store: githubStore(token),
        path: configFile(),
        parse: (text: string) => text,
        serialize: (text: string) => text,
        transform: (text: string) => configTextFor(text, transform(parseConfig(text))),
        message,
      });
      setS(p => ({
        ...p,
        config: parseConfig(result.value),
        cfgSha: result.sha,
        saveError: null,
      }));
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
    <C.Provider
      value={{
        ...onScreen,
        reload,
        mutateSpeakers,
        mutateConfig,
        queueSpeakerEdit,
        flushSpeakers,
        pendingEdits: pendingCount(queue),
        clearSaveError,
      }}
    >
      {children}
    </C.Provider>
  );
}

export function useData() {
  const c = useContext(C);
  if (!c) throw new Error('useData outside provider');
  return c;
}
