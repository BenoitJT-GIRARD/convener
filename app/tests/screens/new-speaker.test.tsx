import { describe, it, expect, vi, beforeEach } from 'vitest';
import { boardYaml, configYaml, speaker as double } from '../helpers/data-doubles';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from '../../src/auth/AuthContext';
import { DataProvider } from '../../src/data/DataContext';
import { NewSpeaker } from '../../src/screens/NewSpeaker';
import { parseSpeakers, serializeSpeakers } from '../../src/data/yaml';
import type { Speaker } from '../../src/data/types';

/** An existing record in the file, from the shared double: what this file
 *  is about is the id the form computes next, not the shape of a speaker. */
function speaker(id: string): Speaker {
  return double({ id, name: `Speaker ${id}` });
}

function encodeUtf8(text: string): string {
  const bytes = new TextEncoder().encode(text);
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function decodeUtf8(b64: string): string {
  const bin = atob(b64);
  const bytes = Uint8Array.from(bin, c => c.charCodeAt(0));
  return new TextDecoder('utf-8').decode(bytes);
}

/** A minimal stand-in for the GitHub Contents API that enforces the sha
 *  precondition, like the real API does, so a stale write is rejected. */
function makeSpeakersBackend(initial: Speaker[], cfgYaml = configYaml()) {
  let server = initial;
  let sha = 'sha-0';
  let counter = 0;
  const messages: string[] = [];

  const fetchMock = vi.fn((url: string, opts?: RequestInit) => {
    if (url.includes('/user')) {
      return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
    }
    if (url.includes('speakers.yml')) {
      if (opts?.method === 'PUT') {
        const body = JSON.parse(opts.body as string);
        if (body.sha !== sha) {
          return Promise.resolve({ ok: false, status: 409, text: async () => 'stale sha' });
        }
        messages.push(body.message as string);
        server = parseSpeakers(decodeUtf8(body.content));
        sha = `sha-${++counter}`;
        return Promise.resolve({ ok: true, json: async () => ({ content: { sha } }) });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ content: encodeUtf8(serializeSpeakers(server)), sha }),
      });
    }
    return Promise.resolve({ ok: true, json: async () => ({ content: encodeUtf8(cfgYaml), sha: 'cfgsha' }) });
  });

  return {
    fetchMock,
    /** Every commit subject this UI actually sent, in order. */
    messages,
    /** Simulate another submitter's write landing directly on the remote,
     *  bypassing this test's UI and this component's local React state. */
    interlope(next: Speaker[]) {
      server = next;
      sha = `sha-other-${++counter}`;
    },
    current: () => server,
  };
}

/** Every PUT is rejected as stale, no matter the sha sent — `mutate` exhausts
 *  its retries and `mutateSpeakers` resolves `false`. */
function makeAlwaysConflictingBackend(initial: Speaker[]) {
  const cfgYaml = configYaml();
  const fetchMock = vi.fn((url: string, opts?: RequestInit) => {
    if (url.includes('/user')) {
      return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
    }
    if (url.includes('speakers.yml')) {
      if (opts?.method === 'PUT') {
        return Promise.resolve({ ok: false, status: 409, text: async () => 'stale sha' });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ content: encodeUtf8(serializeSpeakers(initial)), sha: 'sha-0' }),
      });
    }
    return Promise.resolve({ ok: true, json: async () => ({ content: encodeUtf8(cfgYaml), sha: 'cfgsha' }) });
  });
  return { fetchMock };
}

describe('NewSpeaker', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    localStorage.setItem('convener.token', 'tok');
  });

  it('computes each new id from a fresh read, so a concurrent addition never collides', async () => {
    const backend = makeSpeakersBackend([speaker('spk-001')]);
    vi.stubGlobal('fetch', backend.fetchMock);

    render(
      <MemoryRouter>
        <AuthProvider>
          <DataProvider>
            <NewSpeaker />
          </DataProvider>
        </AuthProvider>
      </MemoryRouter>,
    );

    const nameInput = await screen.findByLabelText(/Name \*/);

    fireEvent.change(nameInput, { target: { value: 'First Lead' } });
    // The submit button stays disabled until config.yml has arrived, since
    // the new lead's owner is computed from the board it holds.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Create lead' })).not.toBeDisabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Create lead' }));
    await waitFor(() => expect(backend.current()).toHaveLength(2));
    expect(backend.current().map(s => s.id)).toEqual(['spk-001', 'spk-002']);

    // A second submitter's lead lands directly on the remote in between —
    // this component's own state has no idea a 'spk-003' now exists.
    backend.interlope([...backend.current(), speaker('spk-003')]);

    fireEvent.change(nameInput, { target: { value: 'Second Lead' } });
    // The submit button stays disabled until config.yml has arrived, since
    // the new lead's owner is computed from the board it holds.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Create lead' })).not.toBeDisabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Create lead' }));
    await waitFor(() => expect(backend.current()).toHaveLength(4));

    const ids = backend.current().map(s => s.id);
    expect(new Set(ids).size).toBe(4); // all distinct — no collision with spk-003
    expect(ids).toContain('spk-004');
  });

  it('commits the new record by its id, never by the researcher it names', async () => {
    // The subject a review found: `data: add lead Jane Doe`, in a
    // history nothing rewrites and every watcher is mailed. What stops it
    // now is the grammar and the `Subject` brand, but neither is read by a
    // test that never looks at what was sent -- so this looks.
    const backend = makeSpeakersBackend([], boardYaml(['alice', 'bob']));
    vi.stubGlobal('fetch', backend.fetchMock);

    render(
      <MemoryRouter>
        <AuthProvider>
          <DataProvider>
            <NewSpeaker />
          </DataProvider>
        </AuthProvider>
      </MemoryRouter>,
    );

    const nameInput = await screen.findByLabelText(/Name \*/);
    fireEvent.change(nameInput, { target: { value: 'Jane Doe' } });
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Create lead' })).not.toBeDisabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Create lead' }));
    await waitFor(() => expect(backend.messages).toHaveLength(1));

    expect(backend.messages[0]).toBe('data: record a new lead for spk-001 by alice');
    expect(backend.messages[0]).not.toContain('Jane');
    expect(backend.messages[0]).not.toContain('Doe');
  });

  it('gives a lead created in the app an owner, by the same rotation the public form uses', async () => {
    const board = boardYaml(['alice', 'bob']);
    const backend = makeSpeakersBackend([], board);
    vi.stubGlobal('fetch', backend.fetchMock);

    render(
      <MemoryRouter>
        <AuthProvider>
          <DataProvider>
            <NewSpeaker />
          </DataProvider>
        </AuthProvider>
      </MemoryRouter>,
    );

    const nameInput = await screen.findByLabelText(/Name \*/);
    const proposedBy = screen.getByLabelText('Proposed by');

    fireEvent.change(nameInput, { target: { value: 'First Lead' } });
    fireEvent.change(proposedBy, { target: { value: 'a colleague at the conference' } });
    // The submit button stays disabled until config.yml has arrived, since
    // the new lead's owner is computed from the board it holds.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Create lead' })).not.toBeDisabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Create lead' }));
    await waitFor(() => expect(backend.current()).toHaveLength(1));

    // Nobody carries an open lead yet, so the rotation falls to the first
    // eligible member alphabetically.
    expect(backend.current()[0].assigned_to).toBe('alice');
    // ...and the submitter's self-reported name survives untouched: it is the
    // record of who to tell if the board declines.
    expect(backend.current()[0].proposed_by).toBe('a colleague at the conference');

    fireEvent.change(nameInput, { target: { value: 'Second Lead' } });
    // The submit button stays disabled until config.yml has arrived, since
    // the new lead's owner is computed from the board it holds.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Create lead' })).not.toBeDisabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Create lead' }));
    await waitFor(() => expect(backend.current()).toHaveLength(2));

    // Alice now carries one open lead, so the next one goes to Bob — counted
    // from the list read at write time, not from a render-time snapshot.
    expect(backend.current()[1].assigned_to).toBe('bob');
  });

  it('leaves a lead unassigned when the board is empty rather than failing the creation', async () => {
    const backend = makeSpeakersBackend([]);
    vi.stubGlobal('fetch', backend.fetchMock);

    render(
      <MemoryRouter>
        <AuthProvider>
          <DataProvider>
            <NewSpeaker />
          </DataProvider>
        </AuthProvider>
      </MemoryRouter>,
    );

    const nameInput = await screen.findByLabelText(/Name \*/);
    fireEvent.change(nameInput, { target: { value: 'Ownerless Lead' } });
    // The submit button stays disabled until config.yml has arrived, since
    // the new lead's owner is computed from the board it holds.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Create lead' })).not.toBeDisabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Create lead' }));
    await waitFor(() => expect(backend.current()).toHaveLength(1));

    expect(backend.current()[0].assigned_to).toBe('');
  });

  it('does not navigate to a speaker page for a record that failed to write', async () => {
    const backend = makeAlwaysConflictingBackend([speaker('spk-001')]);
    vi.stubGlobal('fetch', backend.fetchMock);

    render(
      <MemoryRouter initialEntries={['/']}>
        <AuthProvider>
          <DataProvider>
            <Routes>
              <Route path="/speakers/:id" element={<div>SPEAKER PAGE</div>} />
              <Route path="/" element={<NewSpeaker />} />
            </Routes>
          </DataProvider>
        </AuthProvider>
      </MemoryRouter>,
    );

    const nameInput = await screen.findByLabelText(/Name \*/);
    fireEvent.change(nameInput, { target: { value: 'Doomed Lead' } });
    // The submit button stays disabled until config.yml has arrived, since
    // the new lead's owner is computed from the board it holds.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Create lead' })).not.toBeDisabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Create lead' }));

    // Wait for the (failing) submit to finish — the button re-enables via
    // `finally` once `mutateSpeakers` settles.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Create lead' })).not.toBeDisabled(),
    );

    expect(screen.queryByText('SPEAKER PAGE')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create lead' })).toBeInTheDocument();
  });
});
