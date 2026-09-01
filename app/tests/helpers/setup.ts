import '@testing-library/jest-dom';
import { beforeEach, vi } from 'vitest';

// The suite's one hard rule is that no test reaches the network. Every test
// that exercises code touching `fetch` stubs it itself (vi.stubGlobal), so
// this default throws instead of silently letting a forgotten stub through
// to a real request -- a failure here fails loudly, in the test that forgot
// the stub, not as a flaky network call.
beforeEach(() => {
  vi.stubGlobal('fetch', () => {
    throw new Error(
      "fetch() was called without being stubbed. Tests must never touch the network -- " +
        "add vi.stubGlobal('fetch', ...) for this test.",
    );
  });
});
