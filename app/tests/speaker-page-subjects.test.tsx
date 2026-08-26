/**
 * The commit subjects the record screen actually sends.
 *
 * `state/decisions.ts` decides what a bookkeeping subject may say, and
 * `decisions.test.ts` holds it to that. This file is the other half: what
 * the screen hands it. The finding was `set ${k}` widened to `set ${k}=${v}`
 * -- a researcher's typed answer in a permanent, unrewritable commit
 * subject, with all 961 tests still green because nothing read the message
 * a save produced. So the message a save produces is read here, for the
 * three writes this screen makes.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from '../src/auth/AuthContext';
import { DataProvider } from '../src/data/DataContext';
import { SpeakerPage } from '../src/screens/SpeakerPage';
import { parseSpeakers, serializeSpeakers } from '../src/data/yaml';
import { configYaml, speaker as double } from './data-doubles';
import type { Speaker } from '../src/data/types';

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

/** The Contents API, enough of it to record what was committed. */
function backend(initial: Speaker[]) {
  let server = initial;
  let sha = 'sha-0';
  let counter = 0;
  const messages: string[] = [];
  const cfg = configYaml();
  const fetchMock = vi.fn((url: string, opts?: RequestInit) => {
    if (url.includes('/user')) {
      return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
    }
    if (url.includes('speakers.yml')) {
      if (opts?.method === 'PUT') {
        const body = JSON.parse(opts.body as string);
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
    return Promise.resolve({
      ok: true,
      json: async () => ({ content: encodeUtf8(cfg), sha: 'cfgsha' }),
    });
  });
  return { fetchMock, messages };
}

function show(s: Speaker) {
  render(
    <MemoryRouter initialEntries={[`/speakers/${s.id}`]}>
      <AuthProvider>
        <DataProvider>
          <Routes>
            <Route path="/speakers/:id" element={<SpeakerPage />} />
          </Routes>
        </DataProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

const delivered = () =>
  double({
    id: 'spk-001',
    name: 'A Speaker',
    status: 'delivered',
    date: '2026-05-01',
    time: '12:30',
    edition_code: 'MRG-1',
    host_1: 'alice',
  });

describe('what the record screen writes down', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    localStorage.setItem('convener.token', 'tok');
  });

  it('names the field that changed and not what was typed into it', async () => {
    const b = backend([delivered()]);
    vi.stubGlobal('fetch', b.fetchMock);
    show(delivered());
    const input = await screen.findByLabelText(/Registrations/i);
    fireEvent.change(input, { target: { value: '128' } });
    await waitFor(() => expect(b.messages).toHaveLength(1));
    expect(b.messages[0]).toBe('data: spk-001 set registrations');
    expect(b.messages[0]).not.toContain('128');
  });

  it('names the line of the runbook that was ticked', async () => {
    const b = backend([delivered()]);
    vi.stubGlobal('fetch', b.fetchMock);
    show(delivered());
    // Found by its own label, not by position in the list: the wrap-up
    // phase gained an earlier checkbox of its own
    // (delivered/recording-retrieved), so "the first checkbox" stopped
    // meaning "the forum summary" -- the subject below still has to name
    // the key belonging to *this* label, whichever position it sits at.
    const label = await screen.findByText(/Forum summary posted/);
    const box = label.closest('div.border')!.querySelector('input[type="checkbox"]');
    if (!(box instanceof HTMLInputElement)) throw new Error('no checkbox found');
    fireEvent.click(box);
    await waitFor(() => expect(b.messages).toHaveLength(1));
    expect(b.messages[0]).toBe('data: spk-001 runbook delivered/forum-summary=true');
  });

  it('names the line an owner was put against, and not the person', async () => {
    const b = backend([delivered()]);
    vi.stubGlobal('fetch', b.fetchMock);
    show(delivered());
    // Found by its own label -- see the test above for why position alone
    // no longer picks out "Registrations" now that the wrap-up phase opens
    // with a different line.
    const label = await screen.findByText('Registrations');
    const owner = label.closest('label')!.parentElement!.querySelector('select');
    if (!(owner instanceof HTMLSelectElement)) throw new Error('no owner select found');
    fireEvent.change(owner, { target: { value: 'alice' } });
    await waitFor(() => expect(b.messages).toHaveLength(1));
    expect(b.messages[0]).toBe('data: spk-001 owner for delivered/registrations');
    expect(b.messages[0]).not.toContain('alice');
  });
});
