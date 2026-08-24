import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { screen, fireEvent, waitFor, act, within } from '@testing-library/react';
import cases from '../../tools/tests/fixtures/governance-cases.json';

// `app/src/islands/survey/main.tsx` is the entry point Vite actually
// builds (`app/vite.config.ts`'s `island-survey` mode) and the module
// `site/src/survey.njk`'s `<script type="module">` tag loads on a real
// survey page. This file tests two things `survey-island.test.tsx`
// cannot, because that file renders `SurveyForm` directly and never
// touches the DOM-bootstrap layer at all:
//
// 1. that the bootstrap actually finds `#survey-form` and reads its
//    `data-event-id`, the same contract `survey.njk` writes to;
// 2. the remount discipline the brief asks every task in this phase to
//    hold -- `app/src/App.tsx`'s former `SurveyRoute` used to give this
//    by keying `<SurveyForm key={eventId} />` on a route match;
//    extracting the form into a router-less island moved that
//    responsibility here, to `mountSurveyIsland`'s own `key={eventId}`,
//    and this suite is what proves it still holds.

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
  const bytes = new Uint8Array(plaintext);
  const end = bytes.indexOf(0);
  const unpadded = end === -1 ? bytes : bytes.slice(0, end);
  return JSON.parse(new TextDecoder().decode(unpadded));
}

/** A second, independent event key pair -- the cross-event test needs two
 *  events with two different keys to prove a response is never encrypted
 *  under the wrong one. */
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

function stubReadyFetch(pem: string = VALID_PEM, enabledIds: string[] = ['mrg-042']) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const u = String(url);
      if (u.match(/\/keys\/events\/.+\.pub$/)) {
        return { ok: true, text: async () => pem } as Response;
      }
      if (u.endsWith('/survey-status.json')) {
        return { ok: true, json: async () => enabledIds } as Response;
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
  it('exports the exact id survey.njk mounts onto', async () => {
    const mod = await import('../src/islands/survey/main');
    expect(mod.MOUNT_ID).toBe('survey-form');
  });

  it('does nothing, and does not throw, when the page has no mount element', async () => {
    expect(document.getElementById('survey-form')).toBeNull();
    await expect(import('../src/islands/survey/main')).resolves.toBeDefined();
  });

  it('auto-bootstraps onto #survey-form at import time, reading its data-event-id', async () => {
    stubReadyFetch();
    const el = document.createElement('div');
    el.id = 'survey-form';
    el.dataset.eventId = 'mrg-042';
    document.body.appendChild(el);

    await import('../src/islands/survey/main');

    await screen.findByRole('group', { name: /rate this session overall/i });
    const calls = vi.mocked(fetch).mock.calls.map(c => String(c[0]));
    expect(calls.some(u => /\/keys\/events\/mrg-042\.pub$/.test(u))).toBe(true);
  });

  it('treats a mount element with no data-event-id as no event id at all', async () => {
    stubReadyFetch();
    const el = document.createElement('div');
    el.id = 'survey-form';
    document.body.appendChild(el);

    await import('../src/islands/survey/main');

    await screen.findByText(/this survey is not available right now/i);
  });
});

describe('mountSurveyIsland -- the remount discipline', () => {
  it("renders SurveyForm keyed by the element's own data-event-id at call time", async () => {
    stubReadyFetch();
    const { mountSurveyIsland } = await import('../src/islands/survey/main');
    const el = document.createElement('div');
    el.dataset.eventId = 'mrg-042';
    document.body.appendChild(el);

    act(() => mountSurveyIsland(el));

    await screen.findByRole('group', { name: /rate this session overall/i });
    const calls = vi.mocked(fetch).mock.calls.map(c => String(c[0]));
    expect(calls.some(u => /\/keys\/events\/mrg-042\.pub$/.test(u))).toBe(true);
  });

  it("forces a full remount -- wiping whatever was answered -- when the mount element's data-event-id changes", async () => {
    // This is the exact defence `app/src/App.tsx`'s former `SurveyRoute`
    // used to give this component before the extraction (see git
    // history): `key={eventId}` on the element passed to `.render()`.
    // Without it, a changed event id merely updates a mounted instance's
    // props -- the answer already ticked below, and `pageState`'s
    // already-fetched key, would both survive past the point where they
    // stopped matching the id a participant is actually about to submit
    // under.
    const eventA = await generateEventKeyPair();
    const eventB = await generateEventKeyPair();
    const { mountSurveyIsland } = await import('../src/islands/survey/main');
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
        if (u.endsWith('/survey-status.json')) {
          return { ok: true, json: async () => ['mrg-042', 'mrg-043'] } as Response;
        }
        throw new Error(`unexpected fetch in test: ${u}`);
      }),
    );

    act(() => mountSurveyIsland(el));
    const ratingGroup = await screen.findByRole('group', { name: /rate this session overall/i });
    fireEvent.click(within(ratingGroup).getAllByRole('radio')[4]); // 5

    el.dataset.eventId = 'mrg-043';
    act(() => mountSurveyIsland(el));

    // A fresh instance -- the earlier selection must not have survived
    // the switch, which is the remount actually taking effect, not
    // merely the right key eventually being fetched.
    const freshGroup = await screen.findByRole('group', { name: /rate this session overall/i });
    expect(
      within(freshGroup)
        .getAllByRole('radio')
        .every(r => !(r as HTMLInputElement).checked),
    ).toBe(true);

    fireEvent.click(within(freshGroup).getAllByRole('radio')[4]); // 5
    fireEvent.click(screen.getByRole('radio', { name: 'Yes' }));

    vi.stubEnv('VITE_SIGNUP_RELAY_URL', 'https://signup-relay.example/');
    const calls: { body: string }[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, opts?: RequestInit) => {
        const u = String(url);
        if (u.endsWith('/keys/events/mrg-043.pub')) {
          return { ok: true, text: async () => eventB.publicPem } as Response;
        }
        if (u === 'https://signup-relay.example/survey') {
          calls.push({ body: String(opts?.body ?? '') });
          return { ok: true } as Response;
        }
        throw new Error(`unexpected fetch in test: ${u}`);
      }),
    );
    fireEvent.click(screen.getByRole('button', { name: /submit/i }));
    await screen.findByText(/your answers have been sent/i);

    expect(calls).toHaveLength(1);
    const sent = JSON.parse(calls[0].body);
    expect(sent.event_id).toBe('mrg-043');

    // The decisive check: only mrg-043's own private key can recover this.
    // If the stale mrg-042 public key had sealed this response instead --
    // the bug this test targets -- decrypting with mrg-043's private key
    // would throw, since RSA-OAEP cannot be decrypted under the wrong
    // key, rather than silently recovering the wrong plaintext.
    const recovered = await decryptEnvelopeFields(eventB.privateKey, sent);
    expect(recovered).toEqual({ overall_rating: 5, recommend: true, feedback: '' });
  });

  it('reuses the same React root on a second call rather than creating a new one', async () => {
    // React itself warns loudly (`console.error`) when `createRoot` is
    // called twice on the same DOM node -- calling `mountSurveyIsland`
    // twice must go through `.render()` on the cached root instead.
    stubReadyFetch();
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      const { mountSurveyIsland } = await import('../src/islands/survey/main');
      const el = document.createElement('div');
      el.dataset.eventId = 'mrg-042';
      document.body.appendChild(el);

      act(() => mountSurveyIsland(el));
      await screen.findByRole('group', { name: /rate this session overall/i });
      act(() => mountSurveyIsland(el));
      await screen.findByRole('group', { name: /rate this session overall/i });

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
describe('mountSurveyIsland -- what an un-keyed render would look like (documentation, not the shipped behaviour)', () => {
  it('without a key, React would keep the previous instance mounted across a prop change', async () => {
    // This does not call `mountSurveyIsland` -- it renders the same way a
    // *broken* version would (no `key`), directly, so this file documents
    // in code exactly what "break the remount" (this task's mutation)
    // means, and why `mountSurveyIsland`'s own `key={eventId}` is
    // load-bearing rather than decorative.
    const { SurveyForm } = await import('../src/islands/survey/SurveyForm');
    const { createRoot } = await import('react-dom/client');
    const React = await import('react');
    // Both ids must stay 'ready' across the switch -- mrg-043 has to be
    // enabled too, or the effect this component still runs on every
    // `eventId` change (un-keyed or not) would legitimately transition to
    // 'closed' for an event with no survey open, which would prove
    // nothing about the remount discipline this test targets.
    stubReadyFetch(VALID_PEM, ['mrg-042', 'mrg-043']);

    const el = document.createElement('div');
    document.body.appendChild(el);
    const root = createRoot(el);

    act(() => root.render(React.createElement(SurveyForm, { eventId: 'mrg-042' })));
    const ratingGroup = await screen.findByRole('group', { name: /rate this session overall/i });
    fireEvent.click(within(ratingGroup).getAllByRole('radio')[4]); // 5

    act(() => root.render(React.createElement(SurveyForm, { eventId: 'mrg-043' })));
    await waitFor(() =>
      expect(
        screen.getByRole('group', { name: /rate this session overall/i }),
      ).toBeInTheDocument(),
    );

    // The defect `mountSurveyIsland`'s `key` prevents: the same instance,
    // same ticked answer, survives a changed event id.
    const survivedGroup = screen.getByRole('group', { name: /rate this session overall/i });
    expect((within(survivedGroup).getAllByRole('radio')[4] as HTMLInputElement).checked).toBe(
      true,
    );
  });
});
