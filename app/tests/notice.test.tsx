/**
 * The Appropriate Legal Notice the cockpit displays in its own footer.
 *
 * The cockpit is the second of this product's two interactive interfaces,
 * and section 5 of the licence attaches to each of them separately: a
 * modified version's interfaces must display such notices **where the
 * original's do**. A notice on the showcase and none here would leave the
 * cockpit's own fork free of the obligation, which is exactly the half a
 * reader would never think to check.
 *
 * Asserted against a rendered `Layout`, not against the module's source.
 * What makes the line carry weight is that a person using the cockpit sees
 * it; a component that imports the notice and never prints it would satisfy
 * any check made on the import.
 *
 * And asserted field by field, against `NOTICE.json` itself rather than
 * against sentences retyped here. Two reasons, and the second is the one
 * that matters: a copy here would have to be edited in step with the
 * declaration, which is the drift this project spends its time deleting --
 * and the way a notice actually decays is one clause at a time, a footer
 * trimmed for width keeping the name and dropping the warranty, so each
 * clause is looked for on its own.
 *
 * `tools/tests/repository/test_notice.py` holds the declaration, the licence and the
 * added term under section 7; `tools/tests/repository/test_site.py` holds the
 * showcase's own rendered colophon. Neither says anything about this one.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider } from '../src/auth/AuthContext';
import { DataProvider } from '../src/data/DataContext';
import { Layout } from '../src/components/Layout';

/** The one declaration, read from the repository the same file the two
 *  build-time readers read. */
const NOTICE = JSON.parse(
  readFileSync(resolve(__dirname, '../../NOTICE.json'), 'utf-8'),
) as Record<string, string>;

/** Every field of it that has to reach the footer. `licence_url` is left
 *  out of this list and checked as an `href` below, because an address in
 *  running text is not a way to read the licence. */
const DISPLAYED = ['product', 'copyright', 'terms', 'warranty', 'licence_name'];

function renderCockpit() {
  // Signed out, so `DataProvider` has nothing to fetch; the stub is here
  // for the suite's own rule that no test may reach the network, not
  // because anything below expects an answer.
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve({ ok: false, status: 404, text: async () => 'no' })),
  );
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

beforeEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe('the notice reaches the browser or the build is broken', () => {
  it('throws when the bundle carries no notice at all', async () => {
    vi.resetModules();
    vi.stubEnv('VITE_PRODUCT_NOTICE', '');
    const { productNotice } = await import('../src/notice');
    expect(() => productNotice()).toThrow(/VITE_PRODUCT_NOTICE/);
  });

  it('reads back exactly what the declaration holds', async () => {
    vi.resetModules();
    const { productNotice } = await import('../src/notice');
    const read = productNotice() as unknown as Record<string, string>;
    for (const field of [...DISPLAYED, 'licence_url']) {
      expect(read[field]).toBe(NOTICE[field]);
    }
  });
});

describe("the cockpit's footer", () => {
  it('displays every clause the notice is made of', () => {
    renderCockpit();
    const footer = screen.getByRole('contentinfo');
    expect(DISPLAYED.length).toBeGreaterThan(0);
    for (const field of DISPLAYED) {
      expect(footer.textContent).toContain(NOTICE[field]);
    }
  });

  it('says how to read the licence, as a licence link and not as prose', () => {
    renderCockpit();
    const link = screen.getByRole('link', { name: NOTICE.licence_name });
    expect(link).toHaveAttribute('href', NOTICE.licence_url);
    // `rel="license"` is what makes it the licence link rather than one
    // more address in a footer -- the same relation the showcase's
    // colophon carries.
    expect(link).toHaveAttribute('rel', 'license');
  });
});
