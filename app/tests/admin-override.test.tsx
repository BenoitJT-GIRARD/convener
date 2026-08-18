import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from '../src/auth/AuthContext';
import { DataProvider } from '../src/data/DataContext';
import { AdminOverride } from '../src/components/AdminOverride';
import { parseSpeakers, serializeSpeakers } from '../src/data/yaml';
import type { Speaker } from '../src/data/types';

function speaker(overrides: Partial<Speaker> = {}): Speaker {
  return {
    id: 'spk-001', name: 'Original Name', gender: 'undisclosed', email: '',
    affiliation: '', country: '', title: '', abstract: '',
    conflicts_of_interest: '', source: 'organizer', proposed_by: '', links: [],
    host_1: '', host_2: '', status: 'lead',
    selection: { votes_for: [], decided_on: '' }, edition_code: '',
    date: '', time: '', zoom_link: '', youtube_url: '', forum_thread: '',
    runbook_progress: {}, notes: '',
    metrics: { registrations: null, live_peak: null, youtube_views_30d: null, forum_replies: null },
    ...overrides,
  };
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

/** A minimal stand-in for the GitHub Contents API that actually enforces the
 *  sha precondition, so a stale write is rejected like the real API would. */
function makeSpeakersBackend(initial: Speaker[]) {
  let server = initial;
  let sha = 'sha-0';
  let counter = 0;
  const cfgYaml = 'season: 2026\nboard_members: []\n';

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
    /** Simulate a concurrent writer committing directly, bypassing this test's UI. */
    interlope(next: Speaker[]) {
      server = next;
      sha = `sha-other-${++counter}`;
    },
    current: () => server,
  };
}

/** Every PUT is rejected as stale, no matter the sha sent — `mutate` exhausts
 *  its retries and the caller's `mutateSpeakers` resolves `false`. */
function makeAlwaysConflictingBackend(initial: Speaker[]) {
  const cfgYaml = 'season: 2026\nboard_members: []\n';
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

describe('AdminOverride EditFields', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    localStorage.setItem('convener.token', 'tok');
  });

  it('does not revert a field a concurrent writer changed that this form never exposes', async () => {
    const original = speaker();
    const backend = makeSpeakersBackend([original]);
    vi.stubGlobal('fetch', backend.fetchMock);

    render(
      <MemoryRouter>
        <AuthProvider>
          <DataProvider>
            <AdminOverride speaker={original} />
          </DataProvider>
        </AuthProvider>
      </MemoryRouter>,
    );

    const nameInput = await screen.findByDisplayValue('Original Name');

    // A concurrent writer (e.g. ForceStatus, in another tab) changes `status`
    // — a field this EditFields form has no input for — directly on the
    // remote. This component's local `draft` state has no idea it happened.
    backend.interlope(
      backend.current().map(s => (s.id === original.id ? { ...s, status: 'approved' } : s)),
    );

    fireEvent.change(nameInput, { target: { value: 'Edited Name' } });
    fireEvent.click(screen.getByText('Save changes'));

    await waitFor(() => expect(screen.getByText('✓ saved')).toBeInTheDocument());

    // The concurrent status change must survive this form's save...
    expect(backend.current()[0].status).toBe('approved');
    // ...and this form's own edit must still have been applied.
    expect(backend.current()[0].name).toBe('Edited Name');
  });

  it('does not revert a concurrent change to a metrics subfield the user did not touch', async () => {
    const original = speaker();
    const backend = makeSpeakersBackend([original]);
    vi.stubGlobal('fetch', backend.fetchMock);

    render(
      <MemoryRouter>
        <AuthProvider>
          <DataProvider>
            <AdminOverride speaker={original} />
          </DataProvider>
        </AuthProvider>
      </MemoryRouter>,
    );

    const nameInput = await screen.findByDisplayValue('Original Name');

    // Concurrent writer (e.g. Archive's metrics editor) sets
    // metrics.youtube_views_30d directly on the remote. This form's `draft`
    // has no idea it happened, and the user never touches that input.
    backend.interlope(
      backend.current().map(s =>
        s.id === original.id
          ? { ...s, metrics: { ...s.metrics, youtube_views_30d: 500 } }
          : s,
      ),
    );

    fireEvent.change(nameInput, { target: { value: 'Edited Name' } });
    fireEvent.click(screen.getByText('Save changes'));

    await waitFor(() => expect(screen.getByText('✓ saved')).toBeInTheDocument());

    // The concurrent metrics change must survive this form's save...
    expect(backend.current()[0].metrics.youtube_views_30d).toBe(500);
    // ...and this form's own edit must still have been applied.
    expect(backend.current()[0].name).toBe('Edited Name');
  });

  it('does not revert a concurrent change to youtube_url the user did not touch', async () => {
    const original = speaker();
    const backend = makeSpeakersBackend([original]);
    vi.stubGlobal('fetch', backend.fetchMock);

    render(
      <MemoryRouter>
        <AuthProvider>
          <DataProvider>
            <AdminOverride speaker={original} />
          </DataProvider>
        </AuthProvider>
      </MemoryRouter>,
    );

    const nameInput = await screen.findByDisplayValue('Original Name');

    // Concurrent writer sets youtube_url directly on the remote — a field
    // this form has an input for, but the user never touches it here.
    backend.interlope(
      backend.current().map(s =>
        s.id === original.id ? { ...s, youtube_url: 'https://youtu.be/concurrent' } : s,
      ),
    );

    fireEvent.change(nameInput, { target: { value: 'Edited Name' } });
    fireEvent.click(screen.getByText('Save changes'));

    await waitFor(() => expect(screen.getByText('✓ saved')).toBeInTheDocument());

    expect(backend.current()[0].youtube_url).toBe('https://youtu.be/concurrent');
    expect(backend.current()[0].name).toBe('Edited Name');
  });

  it('still persists a metrics subfield the user actually changed, alongside other edits', async () => {
    const original = speaker();
    const backend = makeSpeakersBackend([original]);
    vi.stubGlobal('fetch', backend.fetchMock);

    render(
      <MemoryRouter>
        <AuthProvider>
          <DataProvider>
            <AdminOverride speaker={original} />
          </DataProvider>
        </AuthProvider>
      </MemoryRouter>,
    );

    const nameInput = await screen.findByDisplayValue('Original Name');
    const ytViewsInput = screen.getByLabelText('YouTube views (30d)');

    fireEvent.change(nameInput, { target: { value: 'Edited Name' } });
    fireEvent.change(ytViewsInput, { target: { value: '250' } });
    fireEvent.click(screen.getByText('Save changes'));

    await waitFor(() => expect(screen.getByText('✓ saved')).toBeInTheDocument());

    // Dirty tracking must not silently drop a real edit — the failure mode
    // opposite to the ones above.
    expect(backend.current()[0].name).toBe('Edited Name');
    expect(backend.current()[0].metrics.youtube_views_30d).toBe(250);
  });

  it('does not show "saved" when the write fails', async () => {
    const original = speaker();
    const backend = makeAlwaysConflictingBackend([original]);
    vi.stubGlobal('fetch', backend.fetchMock);

    render(
      <MemoryRouter>
        <AuthProvider>
          <DataProvider>
            <AdminOverride speaker={original} />
          </DataProvider>
        </AuthProvider>
      </MemoryRouter>,
    );

    const nameInput = await screen.findByDisplayValue('Original Name');
    fireEvent.change(nameInput, { target: { value: 'Edited Name' } });
    fireEvent.click(screen.getByText('Save changes'));

    // Wait for the save attempt to finish (button re-enables via `finally`).
    await waitFor(() => expect(screen.getByText('Save changes')).toBeInTheDocument());

    expect(screen.queryByText('✓ saved')).not.toBeInTheDocument();
  });
});

describe('AdminOverride DeleteSpeaker', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    localStorage.setItem('convener.token', 'tok');
  });

  it('does not navigate away when the delete write fails', async () => {
    const original = speaker();
    const backend = makeAlwaysConflictingBackend([original]);
    vi.stubGlobal('fetch', backend.fetchMock);

    render(
      <MemoryRouter initialEntries={['/speakers/spk-001']}>
        <AuthProvider>
          <DataProvider>
            <Routes>
              <Route path="/pipeline" element={<div>PIPELINE PAGE</div>} />
              <Route path="/speakers/:id" element={<AdminOverride speaker={original} />} />
            </Routes>
          </DataProvider>
        </AuthProvider>
      </MemoryRouter>,
    );

    // Type the exact name to arm the delete button.
    const confirmInput = await screen.findByPlaceholderText(original.name);
    fireEvent.change(confirmInput, { target: { value: original.name } });
    await waitFor(() => expect(screen.getByText('Delete permanently')).not.toBeDisabled());

    fireEvent.click(screen.getByText('Delete permanently'));

    // Give the (failing) write a chance to resolve — the button re-enables
    // via `finally` once `mutateSpeakers` settles.
    await waitFor(() => expect(screen.getByText('Delete permanently')).not.toBeDisabled());

    expect(screen.queryByText('PIPELINE PAGE')).not.toBeInTheDocument();
    expect(screen.getByText('Delete permanently')).toBeInTheDocument();
  });
});
