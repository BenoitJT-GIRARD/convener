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
 */

export interface FileStore {
  read(path: string): Promise<{ text: string; sha: string }>;
  write(
    path: string,
    text: string,
    sha: string,
    message: string,
  ): Promise<{ sha: string }>;
}

export interface MutateOptions<T> {
  store: FileStore;
  path: string;
  parse: (text: string) => T;
  serialize: (value: T) => string;
  transform: (current: T) => T;
  message: string;
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
      const written = await store.write(path, nextText, sha, message);
      return { value: next, sha: written.sha, changed: true, attempts: attempt };
    } catch (error) {
      if (isConflict(error)) continue;
      throw error;
    }
  }

  throw new ConflictError(path, attempts);
}
