/**
 * The cockpit's own way back to the showcase.
 *
 * A deployed instance is five surfaces -- the showcase, the cockpit, and
 * the three islands mounted on public pages: registration, certificate
 * verification and the post-event survey. The showcase is the entry point
 * to all of them, and every one of the islands returns to it through the
 * masthead its page already carries. The cockpit did not: once you were in
 * it, the only links out went to the forum and to the licence. A visitor
 * who reached it from the demonstration's own home page had no way back to
 * the thing they were looking at.
 *
 * Asserted against the rendered chrome rather than against the source, for
 * the reason `notice.test.tsx` gives about the footer it checks: a
 * component that imports an address and never prints it satisfies any
 * check made on the import.
 *
 * **Both screens, because a visitor meets either one first.** `Layout` is
 * the cockpit proper and `Login` is what somebody without an account
 * actually reaches, which makes it the one that needs the way back most.
 * They live in two directories of `app/src/` and carry one edge between
 * them, so the edge is checked once, here, where the component that
 * carries it in the ordinary case lives.
 *
 * `tools/tests/repository/test_navigation.py` is the other half of the
 * same rule: it builds the showcase and refuses a page of it that does not
 * reach all five surfaces, or one of the four static ones that does not
 * come back. Neither half can see the other's, which is why there are two.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider } from '../../src/auth/AuthContext';
import { DataProvider } from '../../src/data/DataContext';
import { Layout } from '../../src/components/Layout';
import { Login } from '../../src/auth/Login';
import { showcasePath } from '../../src/instance';

/** Where the showcase is served, derived exactly as the bundle derives it
 *  -- never a literal here, which would pass just as well the day the
 *  chrome stopped reading the declaration. */
const SHOWCASE = showcasePath();

function stubNetwork() {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve({ ok: false, status: 404, text: async () => 'no' })),
  );
}

function renderCockpit() {
  stubNetwork();
  render(
    <MemoryRouter initialEntries={['/']}>
      <AuthProvider>
        <DataProvider>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<div />} />
            </Route>
          </Routes>
        </DataProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

function renderSignIn() {
  stubNetwork();
  render(
    <MemoryRouter initialEntries={['/']}>
      <AuthProvider>
        <Login />
      </AuthProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe('the way back to the showcase', () => {
  it('is on the cockpit itself', () => {
    renderCockpit();
    const back = screen.getByRole('link', { name: /public site/i });
    expect(back).toHaveAttribute('href', SHOWCASE);
  });

  it('is on the sign-in screen, which is the one a visitor reaches', () => {
    renderSignIn();
    const back = screen.getByRole('link', { name: /public site/i });
    expect(back).toHaveAttribute('href', SHOWCASE);
  });

  it('is a path on this origin, not the address the declaration names', () => {
    // The demonstration is this build served somewhere the declaration
    // does not name, and so is a preview, and so is the assembled tree a
    // screenshot is taken from. An absolute link would take a visitor
    // off whichever of those they were standing on.
    expect(SHOWCASE.startsWith('/')).toBe(true);
    expect(SHOWCASE).not.toContain('://');
    // And it is the showcase's own root rather than the cockpit's: the
    // cockpit is published one segment under it.
    expect(SHOWCASE.endsWith('/')).toBe(true);
    expect(SHOWCASE.endsWith('/app/')).toBe(false);
  });
});
