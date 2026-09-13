import { describe, expect, it, vi } from 'vitest';
import { ConflictError, mutate } from '../../src/github/mutate';
import type { FileStore } from '../../src/github/mutate';
import { dataEdit, identifier } from '../../src/state/decisions';

/** These tests are about replay, conflicts and shas, not about what the
 *  subject says -- but the store writes commits, so there is no plain string
 *  to hand it. One real subject stands in for all of them. */
const SUBJECT = dataEdit(identifier('spk-001'), { part: 'admin-fields' });

/** In-memory store whose `write` rejects a stale sha, like the real API. */
function makeStore(initial: string) {
  let text = initial;
  let sha = 'sha-0';
  let counter = 0;
  /** Failures queued for the next writes, in order. `applied` is the whole
   *  point of the pair: a 502 from a gateway can arrive after the commit was
   *  created, and the two cases are indistinguishable to the caller. */
  const failures: { status: number; applied: boolean }[] = [];
  const store: FileStore = {
    read: vi.fn(async () => ({ text, sha })),
    write: vi.fn(async (_path, nextText, expectedSha) => {
      if (expectedSha !== sha) {
        const err = new Error('stale sha') as Error & { status: number };
        err.status = 409;
        throw err;
      }
      const failure = failures.shift();
      if (failure) {
        if (failure.applied) {
          text = nextText;
          sha = `sha-${++counter}`;
        }
        const err = new Error(`http ${failure.status}`) as Error & { status: number };
        err.status = failure.status;
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
    /** Queue a failure for the next write. `applied` says whether the commit
     *  was created before the failure was returned. */
    failNext: (status: number, applied = false) => failures.push({ status, applied }),
    /** Simulate someone else committing between our read and our write. */
    interlope: (nextText: string) => {
      text = nextText;
      sha = `sha-other-${++counter}`;
    },
  };
}

/** A backoff that records what it was asked to wait rather than waiting. */
function makeWait() {
  const waited: number[] = [];
  return { waited, wait: async (ms: number) => void waited.push(ms) };
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
      message: SUBJECT,
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
      message: SUBJECT,
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
      message: SUBJECT,
    });

    // Both writes survive: the other person's 9 and our 3.
    expect(harness.current()).toBe('1,2,9,3');
  });

  it('gives up with a ConflictError after the attempt budget', async () => {
    const { store } = makeStore('1');
    vi.mocked(store.write).mockImplementation(async () => {
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
        message: SUBJECT,
        attempts: 3,
      }),
    ).rejects.toBeInstanceOf(ConflictError);
    expect(store.write).toHaveBeenCalledTimes(3);
  });

  it('rethrows errors that are not conflicts', async () => {
    const { store } = makeStore('1');
    vi.mocked(store.write).mockImplementation(async () => {
      const err = new Error('forbidden') as Error & { status: number };
      err.status = 403;
      throw err;
    });
    await expect(
      mutate({ store, path: 'data/n.txt', ...numbers, transform: (v) => v.concat(2), message: SUBJECT }),
    ).rejects.toThrow('forbidden');
    expect(store.write).toHaveBeenCalledTimes(1);
  });
});

// ------------------------------------------------------------------ //
// A failure that says nothing about what it did.
// ------------------------------------------------------------------ //

describe('mutate, on a failure that is not a refusal', () => {
  it('replays a 502 that did not land, and waits first', async () => {
    // The case measured on a live instance: Create lead answered "GitHub is
    // not responding", nothing had been written, and pressing the button
    // again worked. This is that second press, taken by the application.
    const { store, current, failNext } = makeStore('1,2');
    const { waited, wait } = makeWait();
    failNext(502);

    const result = await mutate({
      store,
      path: 'data/n.txt',
      ...numbers,
      transform: (v) => [...v, 3],
      message: SUBJECT,
      wait,
    });

    expect(current()).toBe('1,2,3');
    expect(result.changed).toBe(true);
    expect(result.attempts).toBe(2);
    expect(store.write).toHaveBeenCalledTimes(2);
    expect(waited).toEqual([500]);
  });

  it('does not write twice when the failed attempt had already landed', async () => {
    // The reason this is not simply "replay a 5xx". A gateway can return 502
    // after the commit exists, and no caller's transform is idempotent
    // against its own result -- creating a lead appends a record and derives
    // its id from what it reads, so a blind replay is how one speaker becomes
    // two. The next read is what settles it: the file already holds the bytes
    // this attempt tried to write.
    const { store, current, failNext } = makeStore('1,2');
    const { waited, wait } = makeWait();
    failNext(502, true);

    const result = await mutate({
      store,
      path: 'data/n.txt',
      ...numbers,
      transform: (v) => [...v, 3],
      message: SUBJECT,
      wait,
    });

    expect(current()).toBe('1,2,3');
    expect(result.value).toEqual([1, 2, 3]);
    expect(result.changed).toBe(true);
    expect(store.write).toHaveBeenCalledTimes(1);
    expect(waited).toEqual([500]);
  });

  it('stops rather than guess when the file moved and holds something else', async () => {
    // Neither case can be ruled out: the attempt may have been applied and
    // then edited by somebody else, or never applied while they wrote. A
    // replay here could duplicate, so the failure that actually happened is
    // reported instead of guessed at.
    const { store, current, failNext, interlope } = makeStore('1,2');
    const { wait } = makeWait();
    failNext(502, true);

    const attempt = mutate({
      store,
      path: 'data/n.txt',
      ...numbers,
      transform: (v) => [...v, 3],
      message: SUBJECT,
      wait: async (ms) => {
        await wait(ms);
        interlope('1,2,3,9');
      },
    });

    await expect(attempt).rejects.toMatchObject({ status: 502 });
    expect(current()).toBe('1,2,3,9');
    expect(store.write).toHaveBeenCalledTimes(1);
  });

  it('gives up on the failure it had, not on a conflict it never saw', async () => {
    // `ConflictError` tells a volunteer that somebody else is editing at the
    // same time. After three 502s that would be a sentence about a person who
    // does not exist, and it would send them to reload rather than wait.
    const { store, failNext } = makeStore('1,2');
    const { waited, wait } = makeWait();
    failNext(502);
    failNext(503);
    failNext(500);

    const attempt = mutate({
      store,
      path: 'data/n.txt',
      ...numbers,
      transform: (v) => [...v, 3],
      message: SUBJECT,
      wait,
    });

    await expect(attempt).rejects.not.toBeInstanceOf(ConflictError);
    await expect(attempt).rejects.toMatchObject({ status: 500 });
    expect(waited).toEqual([500, 1500]);
  });

  it('replays a 429, which is a request that reached no decision', async () => {
    const { store, current, failNext } = makeStore('1,2');
    const { wait } = makeWait();
    failNext(429);

    await mutate({
      store,
      path: 'data/n.txt',
      ...numbers,
      transform: (v) => [...v, 3],
      message: SUBJECT,
      wait,
    });

    expect(current()).toBe('1,2,3');
    expect(store.write).toHaveBeenCalledTimes(2);
  });

  it('does not replay a 403, which is an answer', async () => {
    // A permission refusal is settled. Replaying it three times would delay
    // the one sentence that helps by two seconds and change nothing.
    const { store, failNext } = makeStore('1,2');
    const { waited, wait } = makeWait();
    failNext(403);

    const attempt = mutate({
      store,
      path: 'data/n.txt',
      ...numbers,
      transform: (v) => [...v, 3],
      message: SUBJECT,
      wait,
    });

    await expect(attempt).rejects.toMatchObject({ status: 403 });
    expect(store.write).toHaveBeenCalledTimes(1);
    expect(waited).toEqual([]);
  });

  it('waits for nothing when the failure is a conflict', async () => {
    // Somebody else has already written; reading again immediately is the
    // point of the replay, and a pause would only widen the window for a
    // third writer.
    const { store, current, interlope } = makeStore('1,2');
    const { waited, wait } = makeWait();
    const once = vi.fn(() => interlope('1,2,9'));

    const result = await mutate({
      store,
      path: 'data/n.txt',
      ...numbers,
      transform: (v) => (v.includes(9) ? [...v, 3] : (once(), [...v, 3])),
      message: SUBJECT,
      wait,
    });

    expect(result.changed).toBe(true);
    expect(current()).toBe('1,2,9,3');
    expect(waited).toEqual([]);
  });
});
