import { describe, expect, it, vi } from 'vitest';
import { ConflictError, mutate } from '../src/github/mutate';
import type { FileStore } from '../src/github/mutate';

/** In-memory store whose `write` rejects a stale sha, like the real API. */
function makeStore(initial: string) {
  let text = initial;
  let sha = 'sha-0';
  let counter = 0;
  const store: FileStore = {
    read: vi.fn(async () => ({ text, sha })),
    write: vi.fn(async (_path, nextText, expectedSha) => {
      if (expectedSha !== sha) {
        const err = new Error('stale sha') as Error & { status: number };
        err.status = 409;
        throw err;
      }
      text = nextText;
      sha = `sha-${++counter}`;
      return { sha };
    }),
  };
  return {
    store,
    current: () => text,
    /** Simulate someone else committing between our read and our write. */
    interlope: (nextText: string) => {
      text = nextText;
      sha = `sha-other-${++counter}`;
    },
  };
}

const numbers = {
  parse: (t: string) => t.split(',').filter(Boolean).map(Number),
  serialize: (v: number[]) => v.join(','),
};

describe('mutate', () => {
  it('applies the transform and writes once when there is no conflict', async () => {
    const { store, current } = makeStore('1,2');
    const result = await mutate({
      store,
      path: 'data/n.txt',
      ...numbers,
      transform: (v) => [...v, 3],
      message: 'add 3',
    });
    expect(current()).toBe('1,2,3');
    expect(result.changed).toBe(true);
    expect(store.write).toHaveBeenCalledTimes(1);
  });

  it('does not write when the transform changes nothing', async () => {
    const { store } = makeStore('1,2');
    const result = await mutate({
      store,
      path: 'data/n.txt',
      ...numbers,
      transform: (v) => v,
      message: 'noop',
    });
    expect(result.changed).toBe(false);
    expect(store.write).not.toHaveBeenCalled();
  });

  it('replays the transform on the fresh version after a conflict', async () => {
    const harness = makeStore('1,2');
    let firstAttempt = true;
    // `store.read` is left at its default implementation, which always
    // reflects the store's current text/sha — including whatever the
    // "interloper" wrote in between our attempts.
    // Someone else appends 9 between our read and our write. Capture the
    // store's underlying write logic (not the mock wrapper — reassigning
    // mockImplementation replaces it in place, so holding a reference to
    // `harness.store.write` itself would recurse into the new behavior).
    const originalWrite = vi.mocked(harness.store.write).getMockImplementation()!;
    vi.mocked(harness.store.write).mockImplementation(
      async (path, text, sha, message) => {
        if (firstAttempt) {
          firstAttempt = false;
          harness.interlope('1,2,9');
          const err = new Error('stale sha') as Error & { status: number };
          err.status = 409;
          throw err;
        }
        return originalWrite(path, text, sha, message);
      },
    );

    await mutate({
      store: harness.store,
      path: 'data/n.txt',
      ...numbers,
      transform: (v) => [...v, 3],
      message: 'add 3',
    });

    // Both writes survive: the other person's 9 and our 3.
    expect(harness.current()).toBe('1,2,9,3');
  });

  it('gives up with a ConflictError after the attempt budget', async () => {
    const { store } = makeStore('1');
    (store.write as ReturnType<typeof vi.fn>).mockImplementation(async () => {
      const err = new Error('stale sha') as Error & { status: number };
      err.status = 409;
      throw err;
    });
    await expect(
      mutate({
        store,
        path: 'data/n.txt',
        ...numbers,
        transform: (v) => [...v, 2],
        message: 'add 2',
        attempts: 3,
      }),
    ).rejects.toBeInstanceOf(ConflictError);
    expect(store.write).toHaveBeenCalledTimes(3);
  });

  it('rethrows errors that are not conflicts', async () => {
    const { store } = makeStore('1');
    (store.write as ReturnType<typeof vi.fn>).mockImplementation(async () => {
      const err = new Error('forbidden') as Error & { status: number };
      err.status = 403;
      throw err;
    });
    await expect(
      mutate({ store, path: 'data/n.txt', ...numbers, transform: (v) => v.concat(2), message: 'x' }),
    ).rejects.toThrow('forbidden');
    expect(store.write).toHaveBeenCalledTimes(1);
  });
});
