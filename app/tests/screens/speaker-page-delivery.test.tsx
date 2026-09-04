/**
 * The passage from a talk that has happened to the wrap-up that follows it.
 *
 * Nothing let a volunteer through it. `effectiveStatus` reported `delivered`
 * as soon as the clock passed the talk, the header printed that, and the
 * checklist under it read the *stored* status and went on showing the
 * scheduled runbook -- so a record whose evening had gone showed a header and
 * a page describing two different states, with no control anywhere to make
 * them agree. That is R40, and it is two fixes: the header stops asserting a
 * status nobody wrote, and the status gains a way out.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from '../../src/auth/AuthContext';
import { DataProvider } from '../../src/data/DataContext';
import { SpeakerPage } from '../../src/screens/SpeakerPage';
import { serializeSpeakers } from '../../src/data/yaml';
import { configYaml, speaker as double } from '../helpers/data-doubles';
import type { Speaker } from '../../src/data/types';

function encodeUtf8(text: string): string {
  const bytes = new TextEncoder().encode(text);
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

/** Read-only: this suite is about what the page says, not what it writes. */
function backend(speakers: Speaker[]) {
  const cfg = configYaml();
  return (url: string) => {
    if (url.includes('/user')) {
      return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
    }
    if (url.includes('speakers.yml')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ content: encodeUtf8(serializeSpeakers(speakers)), sha: 'sha-0' }),
      });
    }
    return Promise.resolve({
      ok: true,
      json: async () => ({ content: encodeUtf8(cfg), sha: 'cfgsha' }),
    });
  };
}

function show(s: Speaker) {
  vi.stubGlobal('fetch', backend([s]));
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

/** A talk on the calendar, still recorded as scheduled. */
function scheduled(date: string): Speaker {
  return double({ id: 'spk-del', status: 'scheduled', date, time: '12:30', edition_code: 'MRG-1' });
}

describe('a talk whose evening has gone', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('convener.token', 'tok');
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date('2026-08-05T10:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('says what the record says, and says separately that the time has passed', async () => {
    show(scheduled('2026-08-01'));
    // The header is the record's own status. It used to read "delivered"
    // above a scheduled runbook.
    await waitFor(() => expect(screen.getByText('scheduled')).toBeInTheDocument());
    expect(screen.queryByText('delivered')).toBeNull();
    expect(screen.getByText(/time has passed/)).toBeInTheDocument();
  });

  it('offers the control that closes the status, at the end of the runbook', async () => {
    show(scheduled('2026-08-01'));
    const button = await screen.findByRole('button', { name: /Mark it delivered/ });
    await waitFor(() => expect(button).not.toBeDisabled());
  });

  it('says nothing about a passing of time that has not happened', async () => {
    show(scheduled('2026-10-01'));
    await waitFor(() => expect(screen.getByText('scheduled')).toBeInTheDocument());
    expect(screen.queryByText(/time has passed/)).toBeNull();
  });

  it('holds the control shut until the day before, and says when it opens', async () => {
    show(scheduled('2026-10-01'));
    const button = await screen.findByRole('button', { name: /Mark it delivered/ });
    expect(button).toBeDisabled();
    expect(screen.getByText(/This opens the day before the talk, which is on 2026-10-01/))
      .toBeInTheDocument();
  });
});
