import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { screen, fireEvent, waitFor, act } from '@testing-library/react';
import cases from '../../../tools/tests/fixtures/governance-cases.json';

// `app/src/islands/signup/main.tsx` is the entry point Vite actually
// builds (`app/vite.config.ts`'s `island-signup` mode) and the module
// `site/src/event.njk`'s `<script type="module">` tag loads on a real
// event page. This file tests two things `signup-island.test.tsx` cannot,
// because that file renders `SignupForm` directly and never touches the
// DOM-bootstrap layer at all:
//
// 1. that the bootstrap actually finds `#registration-form` and reads its
//    `data-event-id`, the same contract `event.njk` writes to;
// 2. the remount discipline every island in this project has to hold --
//    `app/src/App.tsx`'s `SignupRoute` used to give this by
//    keying `<SignupForm key={eventId} />` on a route match; extracting
//    the form into a router-less island moved that responsibility here,
//    to `mountSignupIsland`'s own `key={eventId}`, and this suite is what
//    proves it still holds.

const FIXTURE = cases.event_registration_encryption;
const VALID_PEM = FIXTURE.public_pem;

const RSA_KEY_BITS = 2048;

function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function base64ToBytes(b64: string): Uint8Array<ArrayBuffer> {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function toPem(der: ArrayBuffer, label: string): string {
  const b64 = bytesToBase64(new Uint8Array(der));
  const lines = b64.match(/.{1,64}/g) ?? [b64];
  return `-----BEGIN ${label}-----\n${lines.join('\n')}\n-----END ${label}-----\n`;
}

async function decryptEnvelopeFields(
  privateKey: CryptoKey,
  envelope: { encrypted_key: string; iv: string; ciphertext: string },
): Promise<unknown> {
  const aesKeyBytes = await crypto.subtle.decrypt(
    { name: 'RSA-OAEP' },
    privateKey,
    base64ToBytes(envelope.encrypted_key),
  );
  const aesKey = await crypto.subtle.importKey('raw', aesKeyBytes, { name: 'AES-GCM' }, false, [
    'decrypt',
  ]);
  const plaintext = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: base64ToBytes(envelope.iv) },
    aesKey,
    base64ToBytes(envelope.ciphertext),
  );
  return JSON.parse(new TextDecoder().decode(plaintext));
}

/** A second, independent event key pair -- the cross-event test needs two
 *  events with two different keys to prove a registration is never
 *  encrypted under the wrong one. */
async function generateEventKeyPair(): Promise<{ publicPem: string; privateKey: CryptoKey }> {
  const { publicKey, privateKey } = await crypto.subtle.generateKey(
    {
      name: 'RSA-OAEP',
      modulusLength: RSA_KEY_BITS,
      publicExponent: new Uint8Array([1, 0, 1]),
      hash: 'SHA-256',
    },
    true,
    ['encrypt', 'decrypt'],
  );
  const der = await crypto.subtle.exportKey('spki', publicKey);
  return { publicPem: toPem(der, 'PUBLIC KEY'), privateKey };
}

function stubKeyFetchOk(pem: string = VALID_PEM) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (String(url).match(/\/keys\/events\/.+\.pub$/)) {
        return { ok: true, text: async () => pem } as Response;
      }
      throw new Error(`unexpected fetch in test: ${url}`);
    }),
  );
}

beforeEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.resetModules();
  document.body.innerHTML = '';
});

afterEach(() => {
  document.body.innerHTML = '';
});

describe('main.tsx -- finding and reading the mount point', () => {
  it('exports the exact id event.njk mounts onto', async () => {
    const mod = await import('../../src/islands/signup/main');
    expect(mod.MOUNT_ID).toBe('registration-form');
  });

  it('does nothing, and does not throw, when the page has no mount element', async () => {
    // A past-event page (`{% if isUpcoming %}` in event.njk) ships no
    // `#registration-form` at all, and never loads this script in the
    // first place -- but if it ever did, module-level bootstrap code
    // must not assume the element exists.
    expect(document.getElementById('registration-form')).toBeNull();
    await expect(import('../../src/islands/signup/main')).resolves.toBeDefined();
  });

  it('auto-bootstraps onto #registration-form at import time, reading its data-event-id', async () => {
    stubKeyFetchOk();
    const el = document.createElement('div');
    el.id = 'registration-form';
    el.dataset.eventId = 'mrg-042';
    document.body.appendChild(el);

    await import('../../src/islands/signup/main');

    await screen.findByLabelText(/first name/i);
    expect(String(vi.mocked(fetch).mock.calls[0][0])).toMatch(/\/keys\/events\/mrg-042\.pub$/);
  });

  it('treats a mount element with no data-event-id as no event id at all', async () => {
    stubKeyFetchOk();
    const el = document.createElement('div');
    el.id = 'registration-form';
    document.body.appendChild(el);

    await import('../../src/islands/signup/main');

    await screen.findByText(/registration is not available right now/i);
  });
});

describe('mountSignupIsland -- the remount discipline', () => {
  it('renders SignupForm keyed by the element\'s own data-event-id at call time', async () => {
    stubKeyFetchOk();
    const { mountSignupIsland } = await import('../../src/islands/signup/main');
    const el = document.createElement('div');
    el.dataset.eventId = 'mrg-042';
    document.body.appendChild(el);

    act(() => mountSignupIsland(el));

    await screen.findByLabelText(/first name/i);
    expect(String(vi.mocked(fetch).mock.calls[0][0])).toMatch(/\/keys\/events\/mrg-042\.pub$/);
  });

  it('forces a full remount -- wiping whatever was typed -- when the mount element\'s data-event-id changes', async () => {
    // This is the exact defence `app/src/App.tsx`'s own `SignupRoute` used
    // to give this component before the extraction (see git history):
    // `key={eventId}` on the element passed to `.render()`. Without it, a
    // changed event id merely updates a mounted instance's props -- the
    // typed text below, and `keyState`'s already-fetched key, would both
    // survive past the point where they stopped matching the id a
    // participant is actually about to submit under.
    const eventA = await generateEventKeyPair();
    const eventB = await generateEventKeyPair();
    const { mountSignupIsland } = await import('../../src/islands/signup/main');
    const el = document.createElement('div');
    el.dataset.eventId = 'mrg-042';
    document.body.appendChild(el);

    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        const u = String(url);
        if (u.endsWith('/keys/events/mrg-042.pub')) {
          return { ok: true, text: async () => eventA.publicPem } as Response;
        }
        if (u.endsWith('/keys/events/mrg-043.pub')) {
          return { ok: true, text: async () => eventB.publicPem } as Response;
        }
        throw new Error(`unexpected fetch in test: ${u}`);
      }),
    );

    act(() => mountSignupIsland(el));
    const firstName = await screen.findByLabelText(/first name/i);
    fireEvent.change(firstName, { target: { value: 'stale text from the previous event' } });

    el.dataset.eventId = 'mrg-043';
    act(() => mountSignupIsland(el));

    // A fresh instance -- the earlier text must not have survived the
    // switch, which is the remount actually taking effect, not merely the
    // right key eventually being fetched.
    const freshFirstName = await screen.findByLabelText(/first name/i);
    expect(freshFirstName).toHaveValue('');

    fireEvent.change(freshFirstName, { target: { value: 'Ada' } });
    fireEvent.change(screen.getByLabelText(/surname/i), { target: { value: 'Lovelace' } });
    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: 'ada@example.org' },
    });

    vi.stubEnv('VITE_SIGNUP_RELAY_URL', 'https://signup-relay.example/');
    const calls: { body: string }[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, opts?: RequestInit) => {
        const u = String(url);
        if (u.endsWith('/keys/events/mrg-043.pub')) {
          return { ok: true, text: async () => eventB.publicPem } as Response;
        }
        if (u === 'https://signup-relay.example/') {
          calls.push({ body: String(opts?.body ?? '') });
          return { ok: true } as Response;
        }
        throw new Error(`unexpected fetch in test: ${u}`);
      }),
    );
    fireEvent.click(screen.getByRole('button', { name: /register/i }));
    await screen.findByText(/registration sent/i);

    expect(calls).toHaveLength(1);
    const sent = JSON.parse(calls[0].body);
    expect(sent.event_id).toBe('mrg-043');

    // The decisive check: only mrg-043's own private key can recover this.
    // If the stale mrg-042 public key had sealed this registration instead
    // -- the bug this test targets -- decrypting with mrg-043's private key
    // would throw, since RSA-OAEP cannot be decrypted under the wrong key,
    // rather than silently recovering the wrong plaintext.
    const recovered = await decryptEnvelopeFields(eventB.privateKey, sent);
    expect(recovered).toEqual({
      first_name: 'Ada',
      surname: 'Lovelace',
      email: 'ada@example.org',
      institution: '',
      membership_opt_in: false,
    });
  });

  it('reuses the same React root on a second call rather than creating a new one', async () => {
    // React itself warns loudly (`console.error`) when `createRoot` is
    // called twice on the same DOM node -- calling `mountSignupIsland`
    // twice must go through `.render()` on the cached root instead.
    stubKeyFetchOk();
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      const { mountSignupIsland } = await import('../../src/islands/signup/main');
      const el = document.createElement('div');
      el.dataset.eventId = 'mrg-042';
      document.body.appendChild(el);

      act(() => mountSignupIsland(el));
      await screen.findByLabelText(/first name/i);
      act(() => mountSignupIsland(el));
      await screen.findByLabelText(/first name/i);

      const reactCreateRootWarning = errorSpy.mock.calls.some(args =>
        String(args[0]).includes('createRoot'),
      );
      expect(reactCreateRootWarning).toBe(false);
    } finally {
      errorSpy.mockRestore();
    }
  });
});

// Belt and braces: proves this suite's own remount test would actually
// fail if the discipline were removed, by exercising the un-keyed
// behaviour directly rather than trusting the description above.
describe('mountSignupIsland -- what an un-keyed render would look like (documentation, not the shipped behaviour)', () => {
  it('without a key, React would keep the previous instance mounted across a prop change', async () => {
    // This does not call `mountSignupIsland` -- it renders the same way a
    // *broken* version would (no `key`), directly, so this file documents
    // in code exactly what "break the remount" means, and why
    // `mountSignupIsland`'s own `key={eventId}` is load-
    // bearing rather than decorative.
    const { SignupForm } = await import('../../src/islands/signup/SignupForm');
    const { createRoot } = await import('react-dom/client');
    const React = await import('react');
    stubKeyFetchOk();

    const el = document.createElement('div');
    document.body.appendChild(el);
    const root = createRoot(el);

    act(() => root.render(React.createElement(SignupForm, { eventId: 'mrg-042' })));
    const firstName = await screen.findByLabelText(/first name/i);
    fireEvent.change(firstName, { target: { value: 'stale' } });

    act(() => root.render(React.createElement(SignupForm, { eventId: 'mrg-043' })));
    await waitFor(() => expect(screen.getByLabelText(/first name/i)).toBeInTheDocument());

    // The defect `mountSignupIsland`'s `key` prevents: the same instance,
    // same typed text, survives a changed event id.
    expect(screen.getByLabelText(/first name/i)).toHaveValue('stale');
  });
});
