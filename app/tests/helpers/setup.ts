// The `/vitest` entry point, never the package root. Both add the same
// matchers at runtime; only this one augments `vitest`'s own `Assertion`
// type with them. The root augments the global `jest` namespace instead,
// which reached vitest's types only because `@vitest/expect` extended that
// namespace -- a bridge vitest 5 does not have, and 249 `TS2339` is what
// the suite reports on the day it goes. The import below is what pins that
// down; `app/tsconfig.test.json`'s `types` entry is the same statement for
// the files that do not import this one.
import '@testing-library/jest-dom/vitest';
import { configure } from '@testing-library/dom';
import { beforeEach, vi } from 'vitest';

// How long `findBy*` and `waitFor` wait before giving up.
//
// The default is one second, and it stopped being enough the moment the
// markdown renderer became something the application fetches rather than
// something it ships (`src/content/Markdown.tsx`). Rendering handbook content
// is now two awaits deep -- the text, then the renderer -- and a reading that
// waits for the rendered output has to outlast both.
//
// Measured rather than guessed, because the first diagnosis was wrong: the two
// readings that failed pass on their own and fail inside the full suite, on
// both React 19.2.8 and 19.3.0. So it is not a version and not the boundary;
// it is this suite's own environment, which spends 71% of its time building
// jsdom 109 times over, and a one-second window inside that is a window the
// machine's load decides.
//
// Raised here rather than at the two call sites that happened to be caught:
// every reading that renders content has the same exposure, and two of them
// being slow enough today is not a reason to treat only those two. This is a
// patience setting, not a tolerance for broken output -- a test whose content
// never arrives still fails, five seconds later instead of one.
configure({ asyncUtilTimeout: 5000 });

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
