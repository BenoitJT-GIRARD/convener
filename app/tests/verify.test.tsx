import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { VerifyPage } from '../src/verify/VerifyPage';
import cases from '../../tools/tests/fixtures/certificate-verification.json';

/**
 * End-to-end tests of the whole route: real fixture tokens, real RSA
 * verification via `crypto.subtle` (never a stubbed `verify()`), a stubbed
 * `fetch` standing in for the two same-origin static files this page reads
 * (`keys/signing/index.json`, `certificates.json`). This is what a unit
 * test of `verify.ts` alone cannot prove: that `VerifyPage` actually wires
 * a genuine signature failure to the "not verifiable" panel, and a genuine
 * register-unavailable to "state unknown" -- not merely that the pure
 * functions are correct in isolation.
 */

const SIGNED = cases.signed_example;
const REAL_PROJECTION = cases.projection_example.certificates;

function pathFor(identifier: string, token?: string): string {
  return token ? `/verify/${identifier}?token=${encodeURIComponent(token)}` : `/verify/${identifier}`;
}

function stubFetch(options: {
  keys?: string[] | 'fail';
  projection?: unknown[] | 'fail';
}) {
  const { keys = [SIGNED.public_pem], projection = REAL_PROJECTION } = options;
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

function renderVerify(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/verify/:identifier" element={<VerifyPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the route shape matches what certificate.verification_url actually produces', () => {
  it('the path this test builds for the signed fixture equals the fragment of the fixture\'s own verification_url', () => {
    // certificate.VERIFICATION_BASE ends "#/verify/" -- everything after
    // "#" is what a HashRouter (and this test's MemoryRouter, standing in
    // for it) treats as the path. If this ever drifts from what
    // certificate.py actually builds, this is what would catch it.
    const fragment = SIGNED.verification_url.split('#')[1];
    expect(pathFor(SIGNED.identifier, SIGNED.token)).toBe(fragment);
  });
});

describe('VerifyPage -- with a token', () => {
  it('valid: genuine signature, register says issued', async () => {
    stubFetch({});
    renderVerify(pathFor(SIGNED.identifier, SIGNED.token));

    await screen.findByText('Certificate verified');
    expect(screen.getByText(SIGNED.payload_decoded.name)).toBeInTheDocument();
    expect(screen.getByText(SIGNED.payload_decoded.event)).toBeInTheDocument();
    expect(screen.getByText('1.5 hours')).toBeInTheDocument();
    expect(screen.getByText(SIGNED.identifier)).toBeInTheDocument();
  });

  it('revoked: genuine signature, register says revoked', async () => {
    stubFetch({ projection: [{ identifier: SIGNED.identifier, state: 'revoked' }] });
    renderVerify(pathFor(SIGNED.identifier, SIGNED.token));

    await screen.findByText('Certificate revoked');
    // Genuine and revoked is not an accusation: the name still shows,
    // because the signature really did confirm it (spec S:7's own
    // "Révocation" section: "La signature reste valide").
    expect(screen.getByText(SIGNED.payload_decoded.name)).toBeInTheDocument();
    expect(screen.queryByText('Certificate verified')).not.toBeInTheDocument();
  });

  it('not verifiable: a genuinely truncated token (mutation 1 -- the signature check must not always pass)', async () => {
    const truncated = cases.verification_rejects.find(c => c.name === 'truncated');
    if (!truncated) throw new Error('fixture case not found');
    stubFetch({});
    renderVerify(pathFor(SIGNED.identifier, truncated.token));

    await screen.findByText('We cannot confirm this certificate');
    expect(screen.queryByText('Certificate verified')).not.toBeInTheDocument();
    expect(screen.queryByText('Certificate revoked')).not.toBeInTheDocument();
    // No payload was ever parsed for this outcome -- nothing to show a
    // name from, and nothing here should try.
    expect(screen.queryByText(SIGNED.payload_decoded.name)).not.toBeInTheDocument();
  });

  it('not verifiable: a well-formed token no published key confirms (must not read as "forged")', async () => {
    const differentKey = cases.verification_rejects.find(c => c.name === 'signed by a different key');
    if (!differentKey) throw new Error('fixture case not found');
    stubFetch({});
    renderVerify(pathFor(SIGNED.identifier, differentKey.token));

    await screen.findByText('We cannot confirm this certificate');
    const text = document.body.textContent ?? '';
    expect(text).not.toMatch(/forged|forger|fake/i);
  });

  it('state unknown: genuine signature, register fetch fails (mutation 2 -- must never render "invalid")', async () => {
    stubFetch({ projection: 'fail' });
    renderVerify(pathFor(SIGNED.identifier, SIGNED.token));

    await screen.findByText('We cannot confirm the current state');
    // The signature was genuine, so the name is still shown -- this is
    // exactly the case ruling 2 exists for: an unreadable register must
    // never be presented the same way as an invalid certificate.
    expect(screen.getByText(SIGNED.payload_decoded.name)).toBeInTheDocument();
    expect(screen.queryByText('We cannot confirm this certificate')).not.toBeInTheDocument();
    expect(screen.queryByText('Certificate verified')).not.toBeInTheDocument();
  });

  it('state unknown: genuine signature, identifier genuinely not (yet) in a successfully-read register', async () => {
    stubFetch({ projection: [] });
    renderVerify(pathFor(SIGNED.identifier, SIGNED.token));

    await screen.findByText('We cannot confirm the current state');
  });

  it('never consults the register for a token whose signature does not verify', async () => {
    const truncated = cases.verification_rejects.find(c => c.name === 'truncated');
    if (!truncated) throw new Error('fixture case not found');
    stubFetch({});
    renderVerify(pathFor(SIGNED.identifier, truncated.token));

    await screen.findByText('We cannot confirm this certificate');
    const calls = vi.mocked(fetch).mock.calls.map(call => String(call[0]));
    expect(calls.some(url => url.endsWith('/certificates.json'))).toBe(false);
  });
});

describe('VerifyPage -- no token (the printed-page flow, ruling 5)', () => {
  it('never runs any cryptography and never renders a name -- there is no payload in scope', async () => {
    stubFetch({});
    renderVerify(pathFor(SIGNED.identifier));

    await screen.findByText('Recorded as issued');
    expect(screen.queryByText(SIGNED.payload_decoded.name)).not.toBeInTheDocument();
    expect(screen.queryByText('Name:')).not.toBeInTheDocument();
    // Only the register was asked -- never the signing keys.
    const calls = vi.mocked(fetch).mock.calls.map(call => String(call[0]));
    expect(calls.some(url => url.includes('/keys/signing/'))).toBe(false);
  });

  it('recorded as issued: says it confirmed a record, not a document', async () => {
    stubFetch({});
    renderVerify(pathFor(SIGNED.identifier));

    await screen.findByText('Recorded as issued');
    const text = document.body.textContent ?? '';
    expect(text).toMatch(/record in our register, not the document itself/i);
    expect(text).toMatch(/cannot show a name/i);
  });

  it('recorded as revoked', async () => {
    const revokedRow = REAL_PROJECTION.find(row => row.state === 'revoked');
    if (!revokedRow) throw new Error('fixture missing a revoked row');
    stubFetch({});
    renderVerify(pathFor(revokedRow.identifier));

    await screen.findByText('Recorded as revoked');
  });

  it('not recorded: a decisive fact, distinct from "we do not know"', async () => {
    stubFetch({});
    renderVerify(pathFor('00000000000000000000000000000000'));

    await screen.findByText('Not found in our register');
  });

  it('state unknown: the register could not be read at all', async () => {
    stubFetch({ projection: 'fail' });
    renderVerify(pathFor(SIGNED.identifier));

    await screen.findByText('We cannot confirm this right now');
    expect(screen.queryByText('Not found in our register')).not.toBeInTheDocument();
  });
});

describe('VerifyPage -- a route with no identifier at all', () => {
  it('shows a plain refusal rather than crashing', () => {
    render(
      <MemoryRouter initialEntries={['/verify-nothing']}>
        <Routes>
          <Route path="/verify-nothing" element={<VerifyPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText('No certificate identifier')).toBeInTheDocument();
  });
});

describe('VerifyPage -- the keys fetch itself failing folds into "not verifiable", not a fifth state', () => {
  it('a network error fetching the signing keys', async () => {
    stubFetch({ keys: 'fail' });
    renderVerify(pathFor(SIGNED.identifier, SIGNED.token));

    await screen.findByText('We cannot confirm this certificate');
  });
});

// waitFor imported for readability parity with the rest of the suite even
// where `findBy*` alone suffices above; used explicitly here to assert a
// *negative* (nothing ever renders "Certificate verified") after settling.
describe('VerifyPage -- a tampered signature must never verify (mutation 1, restated)', () => {
  it('one flipped byte in an otherwise well-formed signature', async () => {
    const flipped = cases.verification_rejects.find(c => c.name === 'one byte flipped in the signature');
    if (!flipped) throw new Error('fixture case not found');
    stubFetch({});
    renderVerify(pathFor(SIGNED.identifier, flipped.token));

    await screen.findByText('We cannot confirm this certificate');
    await waitFor(() => {
      expect(screen.queryByText('Certificate verified')).not.toBeInTheDocument();
    });
  });
});
