/**
 * The one wrap-up number the repository can work out for itself.
 *
 * R41 asks for two numbers to fill themselves "where they can", and the
 * measurement is that only one of them can. `registrations.enc` holds one
 * encrypted envelope per person and the *length of that list* is ordinary
 * JSON structure -- no key, nothing about anybody. The peak number in the
 * room is nowhere in this repository at all: the attendance export records
 * who attended, never how many were present at the same moment, so that one
 * stays a field a person fills in from the platform's own live view.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AuthProvider } from '../../src/auth/AuthContext';
import { RegistrationCount } from '../../src/components/RegistrationCount';
import { speaker as double } from '../helpers/data-doubles';

function encodeUtf8(text: string): string {
  const bytes = new TextEncoder().encode(text);
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

/** Whatever the Contents API is standing in for this time, plus the identity
 *  call `AuthProvider` makes on sign-in. */
function backend(reply: (url: string) => unknown) {
  return vi.fn((url: string) => {
    if (url.includes('/user')) {
      return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
    }
    return Promise.resolve(reply(url));
  });
}

function show(onCounted = vi.fn()) {
  render(
    <AuthProvider>
      <RegistrationCount
        speaker={double({ id: 'spk-1', status: 'delivered', edition_code: 'MRG-9' })}
        onCounted={onCounted}
      />
    </AuthProvider>,
  );
  return onCounted;
}

describe('counting the sign-ups', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('convener.token', 'tok');
  });

  afterEach(() => vi.unstubAllGlobals());

  it('reads how many envelopes the file holds, and never their contents', async () => {
    let asked = '';
    vi.stubGlobal(
      'fetch',
      backend(url => {
        asked = url;
        return {
          ok: true,
          json: async () => ({
            content: encodeUtf8(
              JSON.stringify({
                v: 1,
                registrations: [{ iv: 'a' }, { iv: 'b' }, { iv: 'c' }],
              }),
            ),
            sha: 'sha-0',
          }),
        };
      }),
    );
    const onCounted = show();
    fireEvent.click(await screen.findByRole('button', { name: /Count the sign-ups/ }));
    await waitFor(() => expect(onCounted).toHaveBeenCalledWith(3));
    // The event id is the edition code lower-cased, and nothing else.
    expect(asked).toContain('events/mrg-9/registrations.enc');
  });

  it('reads no sign-ups as a normal state, and changes nothing', async () => {
    vi.stubGlobal('fetch', backend(() => ({ ok: false, status: 404, text: async () => 'nope' })));
    const onCounted = show();
    fireEvent.click(await screen.findByRole('button', { name: /Count the sign-ups/ }));
    await waitFor(() =>
      expect(screen.getByText(/No sign-ups are recorded here for this edition/)).toBeInTheDocument(),
    );
    expect(onCounted).not.toHaveBeenCalled();
  });

  it('refuses a file it cannot read as a list, rather than writing a guess', async () => {
    vi.stubGlobal(
      'fetch',
      backend(() => ({
        ok: true,
        json: async () => ({ content: encodeUtf8('{"v": 1}'), sha: 'sha-0' }),
      })),
    );
    const onCounted = show();
    fireEvent.click(await screen.findByRole('button', { name: /Count the sign-ups/ }));
    await waitFor(() =>
      expect(screen.getByText(/not a registration file this app can read/)).toBeInTheDocument(),
    );
    expect(onCounted).not.toHaveBeenCalled();
  });

  it('is absent on a record with no edition code, which has no event yet', () => {
    render(
      <AuthProvider>
        <RegistrationCount speaker={double({ edition_code: '' })} onCounted={vi.fn()} />
      </AuthProvider>,
    );
    expect(screen.queryByRole('button')).toBeNull();
  });
});
