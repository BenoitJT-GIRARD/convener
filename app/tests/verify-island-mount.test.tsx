import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { screen, act } from '@testing-library/react';
import cases from '../../tools/tests/fixtures/certificate-verification.json';

// `app/src/islands/verify/main.tsx` is the entry point Vite actually
// builds (`app/vite.config.ts`'s `island-verify` mode) and the module
// `site/src/verify.njk`'s `<script type="module">` tag loads on the real
// verify page. This file tests what `verify-island.test.tsx` cannot,
// because that file renders `VerifyPage` directly with `identifier`/
// `token` props and never touches the URL-parsing or DOM-bootstrap layers
// at all:
//
// 1. `parseVerificationFragment` actually extracts what
//    `certificate.verification_url` actually produces -- pinned against
//    the shared fixture, the same D-14 discipline
//    `signup-island-mount.test.tsx` does not need (registration reads an
//    attribute, not a URL) but this island does, since the whole reason
//    it exists is to read a fragment safely;
// 2. the bootstrap actually finds `#verify-app` and reads `location.hash`;
// 3. the remount discipline every island in this project has to
//    hold -- `App.tsx`'s old `VerifyRoute` used to give this by keying on
//    a route match, and a second verification link opened in the same tab
//    (same origin, same path, different fragment) is a same-document
//    navigation a browser never reloads for -- `hashchange` is what this
//    island uses instead, and this suite is what proves it still holds.

const SIGNED = cases.signed_example;

beforeEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
  document.body.innerHTML = '';
  window.location.hash = '';
});

afterEach(() => {
  document.body.innerHTML = '';
  window.location.hash = '';
});

function stubFetch(options: { keys?: string[] | 'fail'; projection?: unknown[] | 'fail' } = {}) {
  const { keys = [SIGNED.public_pem], projection = cases.projection_example } = options;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes('/keys/signing/')) {
        if (keys === 'fail') throw new Error('network error');
        return { ok: true, json: async () => keys } as Response;
      }
      if (u.endsWith('/certificates.json')) {
        if (projection === 'fail') return { ok: false, status: 500 } as Response;
        return { ok: true, json: async () => projection } as Response;
      }
      throw new Error(`unexpected fetch in test: ${u}`);
    }),
  );
}

describe('parseVerificationFragment', () => {
  it('reproduces the identifier and token the shared fixture\'s own verification address actually carries', async () => {
    const { parseVerificationFragment } = await import('../src/islands/verify/main');
    // certificate.VERIFICATION_BASE ends "#/" -- everything after "#" is
    // exactly this function's own input once a real browser assigns it to
    // `location.hash`. If this ever drifts from what certificate.py
    // actually builds, this is what would catch it.
    const fragment = `#${SIGNED.verification_url_path.split('#')[1]}`;
    expect(parseVerificationFragment(fragment)).toEqual({
      identifier: SIGNED.identifier,
      token: SIGNED.token,
    });
  });

  it('reads an identifier with no token as identifier-only', async () => {
    const { parseVerificationFragment } = await import('../src/islands/verify/main');
    expect(parseVerificationFragment('#/abc123')).toEqual({ identifier: 'abc123', token: undefined });
  });

  it('tolerates a fragment already stripped of the leading "#/"', async () => {
    const { parseVerificationFragment } = await import('../src/islands/verify/main');
    expect(parseVerificationFragment('abc123?token=xyz')).toEqual({ identifier: 'abc123', token: 'xyz' });
  });

  it('reads an empty hash as neither an identifier nor a token', async () => {
    const { parseVerificationFragment } = await import('../src/islands/verify/main');
    expect(parseVerificationFragment('')).toEqual({ identifier: undefined, token: undefined });
    expect(parseVerificationFragment('#')).toEqual({ identifier: undefined, token: undefined });
    expect(parseVerificationFragment('#/')).toEqual({ identifier: undefined, token: undefined });
  });

  it('falls back to the raw segment rather than throwing on an unparsable percent-sequence', async () => {
    const { parseVerificationFragment } = await import('../src/islands/verify/main');
    expect(parseVerificationFragment('#/not%valid')).toEqual({ identifier: 'not%valid', token: undefined });
  });
});

describe('main.tsx -- finding and reading the mount point', () => {
  it('exports the exact id verify.njk mounts onto', async () => {
    const mod = await import('../src/islands/verify/main');
    expect(mod.MOUNT_ID).toBe('verify-app');
  });

  it('does nothing, and does not throw, when the page has no mount element', async () => {
    expect(document.getElementById('verify-app')).toBeNull();
    await expect(import('../src/islands/verify/main')).resolves.toBeDefined();
  });

  it('auto-bootstraps onto #verify-app at import time, reading the token-less identifier off location.hash', async () => {
    stubFetch({});
    const el = document.createElement('div');
    el.id = 'verify-app';
    document.body.appendChild(el);
    window.location.hash = `#/${SIGNED.identifier}`;

    await import('../src/islands/verify/main');

    await screen.findByText('Recorded as issued');
  });

  it('auto-bootstraps reading both identifier and token off location.hash', async () => {
    stubFetch({});
    const el = document.createElement('div');
    el.id = 'verify-app';
    document.body.appendChild(el);
    window.location.hash = SIGNED.verification_url_path.split('#')[1]
      ? `#${SIGNED.verification_url_path.split('#')[1]}`
      : '';

    await import('../src/islands/verify/main');

    await screen.findByText('Certificate verified');
  });

  it('treats an empty hash as no identifier and no token at all', async () => {
    const el = document.createElement('div');
    el.id = 'verify-app';
    document.body.appendChild(el);

    await import('../src/islands/verify/main');

    await screen.findByText('No certificate identifier');
  });
});

describe('main.tsx -- the remount discipline (hashchange)', () => {
  it('re-renders for a new identifier when the fragment changes, without a full page reload', async () => {
    // A visitor opening a second, different verification link in the same
    // tab -- same origin, same path -- gets a same-document navigation, so
    // this module's own top-level bootstrap never runs a second time.
    // `hashchange` is the only thing that can tell it the URL moved.
    const revokedRow = cases.projection_example.find(row => row.state === 'revoked');
    if (!revokedRow) throw new Error('fixture missing a revoked row');
    stubFetch({});
    const el = document.createElement('div');
    el.id = 'verify-app';
    document.body.appendChild(el);
    window.location.hash = `#/${SIGNED.identifier}`;

    await import('../src/islands/verify/main');
    await screen.findByText('Recorded as issued');

    act(() => {
      window.location.hash = `#/${revokedRow.identifier}`;
      window.dispatchEvent(new Event('hashchange'));
    });

    await screen.findByText('Recorded as revoked');
    expect(screen.queryByText('Recorded as issued')).not.toBeInTheDocument();
  });

  it('shows "Checking…" immediately when the identifier changes, never the previous identifier\'s already-resolved answer (the key= discipline)', async () => {
    // Eventual consistency (the test above) is not the same guarantee as
    // this one: `VerifyTokenless`'s own effect re-fetches on a changed
    // `identifier` regardless of whether `mountVerifyIsland` remounts the
    // whole component, so that test alone would still pass even if the
    // `key={...}` on VerifyPage were removed -- only the *timing* differs,
    // and `findByText` waits it out either way. This test controls the
    // fetch's own resolution so it can inspect the DOM in between: with
    // the key discipline intact, a changed identifier tears the previous
    // instance down and starts a fresh one, whose `lookup` state begins at
    // `'checking'` -- never the *previous* identifier's already-resolved
    // "issued" panel sitting on screen while a different lookup is still
    // in flight.
    const revokedRow = cases.projection_example.find(row => row.state === 'revoked');
    if (!revokedRow) throw new Error('fixture missing a revoked row');

    // `StrictMode` (main.tsx wraps `VerifyPage` in it) double-invokes an
    // effect in development -- mount, cleanup, mount again -- so each real
    // mount below queues *two* fetches, not one; the first's own cleanup
    // sets its `cancelled` flag before it resolves, so only the most
    // recently queued resolver of each pair is the one whose result
    // actually reaches `setLookup`. Resolving the latest resolver each
    // time, rather than assuming exactly one call per mount, is what makes
    // this test robust to that -- an implementation detail of React's own
    // dev-mode behaviour, not of the discipline this test exists to pin.
    const pendingResolvers: Array<(response: Response) => void> = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise<Response>(resolve => pendingResolvers.push(resolve))),
    );

    const { mountVerifyIsland } = await import('../src/islands/verify/main');
    const el = document.createElement('div');
    document.body.appendChild(el);

    act(() => mountVerifyIsland(el, SIGNED.identifier));
    expect(pendingResolvers.length).toBeGreaterThan(0);
    act(() => {
      pendingResolvers.at(-1)!({ ok: true, json: async () => cases.projection_example } as Response);
    });
    await screen.findByText('Recorded as issued');

    const beforeSecondMount = pendingResolvers.length;
    act(() => mountVerifyIsland(el, revokedRow.identifier));

    expect(screen.getByText('Checking…')).toBeInTheDocument();
    expect(screen.queryByText('Recorded as issued')).not.toBeInTheDocument();

    expect(pendingResolvers.length).toBeGreaterThan(beforeSecondMount);
    act(() => {
      pendingResolvers.at(-1)!({ ok: true, json: async () => cases.projection_example } as Response);
    });
    await screen.findByText('Recorded as revoked');
  });
});

// Belt and braces: proves the remount test above would actually fail
// without the listener, by exercising the un-listened behaviour directly
// rather than trusting the description of what `hashchange` buys.
describe('main.tsx -- what no hashchange listener would look like (documentation, not the shipped behaviour)', () => {
  it('without re-reading location.hash, the first render never updates for a later fragment change', async () => {
    const revokedRow = cases.projection_example.find(row => row.state === 'revoked');
    if (!revokedRow) throw new Error('fixture missing a revoked row');
    stubFetch({});
    const { mountVerifyIsland, parseVerificationFragment } = await import('../src/islands/verify/main');
    const el = document.createElement('div');
    document.body.appendChild(el);

    const first = parseVerificationFragment(`#/${SIGNED.identifier}`);
    act(() => mountVerifyIsland(el, first.identifier, first.token));
    await screen.findByText('Recorded as issued');

    // The fragment changes, but nothing calls mountVerifyIsland again --
    // exactly what a missing `hashchange` listener would leave in place.
    window.location.hash = `#/${revokedRow.identifier}`;

    expect(screen.getByText('Recorded as issued')).toBeInTheDocument();
    expect(screen.queryByText('Recorded as revoked')).not.toBeInTheDocument();
  });
});

describe('mountVerifyIsland -- keying discipline', () => {
  it('reuses the same React root on a second call rather than creating a new one', async () => {
    stubFetch({});
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      const { mountVerifyIsland } = await import('../src/islands/verify/main');
      const el = document.createElement('div');
      document.body.appendChild(el);

      act(() => mountVerifyIsland(el, SIGNED.identifier));
      await screen.findByText('Recorded as issued');
      act(() => mountVerifyIsland(el, SIGNED.identifier));
      await screen.findByText('Recorded as issued');

      const reactCreateRootWarning = errorSpy.mock.calls.some(args =>
        String(args[0]).includes('createRoot'),
      );
      expect(reactCreateRootWarning).toBe(false);
    } finally {
      errorSpy.mockRestore();
    }
  });
});
