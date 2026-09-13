/**
 * Transactional writes against a file store.
 *
 * A write is expressed as a *transform* of the current value rather than as
 * a replacement value. When the remote version has moved on, the transform
 * is replayed against the fresh version instead of overwriting it — so two
 * people acting at the same time both keep their change. The transform can
 * be replayed more than once (up to `attempts`), so it must be safe to call
 * repeatedly with a fresh `current` each time; it does not need to be pure
 * in the strict sense of writing nothing outside its return value. A caller
 * that needs something the transform computed along the way (an id it
 * assigned, say) may stash it in a variable in its own closure — the value
 * from the call that actually produced the returned result is the one that
 * matters, and each replay simply overwrites it with a fresh answer.
 *
 * **A failure is replayed only once it is known what it did.** A 409 or 422
 * is a refusal -- the commit was not created -- so the transform is replayed
 * straight away. A 5xx or a 429 says nothing: the write may have been applied
 * at the origin and lost on the way back. Since no caller's transform is
 * idempotent against its own result (creating a lead appends a record and
 * re-derives its id from what it reads), replaying one of those blindly is
 * how a volunteer ends up with two copies of the speaker they entered once.
 * So the next read settles it first -- the file holds what was written, or
 * its sha has not moved, or neither -- and only the middle case is replayed.
 * Until this existed, every 5xx was final on the first attempt and the
 * volunteer was the retry loop.
 *
 * The store is a git repository, so the message this carries is a commit
 * subject: permanent, unrewritable, and mailed to every watcher. It is a
 * `Subject` (`state/decisions.ts`) rather than a `string` for that reason —
 * here as well as at `mutateSpeakers`, so that reaching past the data layer
 * to this function is not a way around the grammar.
 */

import { DecisionRejected, isSubject } from '../state/decisions';
import type { Subject } from '../state/decisions';

export interface FileStore {
  read(path: string): Promise<{ text: string; sha: string }>;
  write(
    path: string,
    text: string,
    sha: string,
    message: Subject,
  ): Promise<{ sha: string }>;
}

export interface MutateOptions<T> {
  store: FileStore;
  path: string;
  parse: (text: string) => T;
  serialize: (value: T) => string;
  transform: (current: T) => T;
  /** The commit subject, or a function from the value about to be written to
   *  it. The function form exists for a subject that has to name something
   *  the transformation assigned -- the id of a record just created, which
   *  `nextSpeakerId(current)` only settles inside the transform and only for
   *  the attempt that actually gets written. Without it the caller would have
   *  to build the subject from a value read before the replay, which is the
   *  one value that may be stale. */
  message: Subject | ((next: T) => Subject);
  attempts?: number;
  /** How the backoff between replays is taken. Injected so the tests can
   *  measure the schedule instead of sitting through it; nothing else has a
   *  reason to pass it. */
  wait?: (ms: number) => Promise<void>;
}

export interface MutateResult<T> {
  value: T;
  sha: string;
  changed: boolean;
  attempts: number;
}

export class ConflictError extends Error {
  constructor(path: string, attempts: number) {
    super(
      `Could not save ${path} after ${attempts} attempts — someone else is ` +
        `editing at the same time. Reload and try again.`,
    );
    this.name = 'ConflictError';
  }
}

function statusOf(error: unknown): number | undefined {
  return (error as { status?: number } | null)?.status;
}

/** A refusal: the Contents API answers 409 on a stale sha, and 422 in some
 *  edge cases. Both say the commit was *not* created, so the transform can be
 *  replayed against a fresh read with nothing to undo and nothing to check. */
function isRefusal(error: unknown): boolean {
  const status = statusOf(error);
  return status === 409 || status === 422;
}

/** A failure that says nothing about what happened. GitHub answered, and
 *  answered that it could not answer: the write may have been applied at the
 *  origin and lost on the way back, or never applied at all. 429 is here for
 *  the same reason and not because it is a server fault -- it is a request
 *  that reached no decision.
 *
 *  A rejected fetch -- offline, DNS, a captive portal -- is deliberately not
 *  on this list. It carries no status because nothing answered, so it is the
 *  one failure where waiting and trying again is least likely to help and
 *  most likely to delay the sentence that actually helps ("check your
 *  connection"), which `friendlyError` already gives it. */
function isUncertain(error: unknown): boolean {
  const status = statusOf(error);
  return status === 429 || (status !== undefined && status >= 500 && status <= 599);
}

/** The pause before each replay of an uncertain failure, in order. Short
 *  enough that three attempts stay inside two seconds -- a volunteer is
 *  watching a button -- and long enough that a 502 has a moment to pass.
 *  A refusal waits for none of this: a conflict means somebody else has
 *  already written, and reading again immediately is the point. */
const BACKOFF_MS: readonly number[] = [500, 1500];

const sleep = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms));

export async function mutate<T>(options: MutateOptions<T>): Promise<MutateResult<T>> {
  const { store, path, parse, serialize, transform, message } = options;
  const attempts = options.attempts ?? 3;
  const wait = options.wait ?? sleep;

  /** Set when an attempt failed without saying whether it was applied. It
   *  carries the sha it wrote against and the bytes it tried to write, which
   *  together are enough for the next read to settle the question. */
  let uncertain: { error: unknown; sha: string; nextText: string } | null = null;

  for (let attempt = 1; attempt <= attempts; attempt++) {
    const { text, sha } = await store.read(path);

    if (uncertain !== null) {
      if (text === uncertain.nextText) {
        // The write landed and the answer was lost on the way back. Replaying
        // here is what would append a second copy of a record that is already
        // there -- every caller's transform is safe to replay against a fresh
        // value, and none of them is idempotent against its own result.
        return { value: parse(text), sha, changed: true, attempts: attempt };
      }
      if (sha !== uncertain.sha) {
        // The file moved and it does not hold what this attempt wrote, so
        // nothing here can tell whether that attempt was applied and then
        // edited, or never applied at all while somebody else wrote. The
        // failure that actually happened is reported rather than guessed at.
        throw uncertain.error;
      }
      // The sha has not moved: the write did not land. Replay is safe.
      uncertain = null;
    }

    const current = parse(text);
    const next = transform(current);
    const nextText = serialize(next);

    if (nextText === text) {
      return { value: current, sha, changed: false, attempts: attempt };
    }

    try {
      const subject = typeof message === 'function' ? message(next) : message;
      // Asked of the string, not of its type. `Subject` is a compile-time
      // fact and a cast is past it in one keystroke; this is the last point
      // before a commit subject becomes permanent, so the grammar is asked
      // here as well. It costs one regex per write and it is the only check
      // in the chain that does not depend on how a defeat was spelled.
      if (!isSubject(subject)) {
        throw new DecisionRejected(
          `"${subject}" is not a commit subject this app assembles. Build it with ` +
            'formatDecision() or dataEdit() in src/state/decisions.ts: a commit ' +
            'subject is permanent and cannot be taken back.',
        );
      }
      const written = await store.write(path, nextText, sha, subject);
      return { value: next, sha: written.sha, changed: true, attempts: attempt };
    } catch (error) {
      if (isRefusal(error)) continue;
      if (isUncertain(error)) {
        uncertain = { error, sha, nextText };
        if (attempt < attempts) {
          await wait(BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length) - 1]);
        }
        continue;
      }
      throw error;
    }
  }

  // An uncertain failure is not a conflict, and must not be reported as one:
  // `ConflictError` tells a volunteer somebody else is editing at the same
  // time, which would be a sentence about a person who does not exist.
  if (uncertain !== null) throw uncertain.error;
  throw new ConflictError(path, attempts);
}
