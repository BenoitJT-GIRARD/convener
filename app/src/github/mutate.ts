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

/** The Contents API answers 409 on a stale sha, and 422 in some edge cases. */
function isConflict(error: unknown): boolean {
  const status = (error as { status?: number } | null)?.status;
  return status === 409 || status === 422;
}

export async function mutate<T>(options: MutateOptions<T>): Promise<MutateResult<T>> {
  const { store, path, parse, serialize, transform, message } = options;
  const attempts = options.attempts ?? 3;

  for (let attempt = 1; attempt <= attempts; attempt++) {
    const { text, sha } = await store.read(path);
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
      if (isConflict(error)) continue;
      throw error;
    }
  }

  throw new ConflictError(path, attempts);
}
