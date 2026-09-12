// The `/vitest` entry point, never the package root. Both add the same
// matchers at runtime; only this one augments `vitest`'s own `Assertion`
// type with them. The root augments the global `jest` namespace instead,
// which reached vitest's types only because `@vitest/expect` extended that
// namespace -- a bridge vitest 5 does not have, and 249 `TS2339` is what
// the suite reports on the day it goes. The import below is what pins that
// down; `app/tsconfig.test.json`'s `types` entry is the same statement for
// the files that do not import this one.
import '@testing-library/jest-dom/vitest';
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
