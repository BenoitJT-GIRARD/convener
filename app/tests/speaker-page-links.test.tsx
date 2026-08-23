/**
 * `s.links` reaches this screen straight from the public, unreviewed
 * proposal intake (`tools/convener_ops/proposal.py::to_lead`) -- a comma-split
 * list of whatever a candidate typed into the "Links" field of the Tally
 * form, with no scheme check anywhere on the Python side. Before this fix,
 * `SpeakerPage` handed every entry to a raw `href` unfiltered: a
 * `javascript:` URI submitted through that same form would sit in a
 * board member's own click, in the operators' cockpit.
 *
 * Security audit 2026-08-23, M3: this codebase already had the fix for the
 * identical problem -- `content/fetch.ts::handbookUrl`'s scheme allowlist
 * -- it was simply not reused here. `isSafeHref`, the allowlist pulled out
 * of that function, is what this test holds `SpeakerPage` to: an unsafe
 * scheme must never reach a raw `href`, a safe one must still render as a
 * real link.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from '../src/auth/AuthContext';
import { DataProvider } from '../src/data/DataContext';
import { SpeakerPage } from '../src/screens/SpeakerPage';
import { serializeSpeakers } from '../src/data/yaml';
import { configYaml, speaker as double } from './data-doubles';
import type { Speaker } from '../src/data/types';

function encodeUtf8(text: string): string {
  const bytes = new TextEncoder().encode(text);
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

/** A read-only stand-in for the Contents API: enough to load one speaker
 *  record and its config, nothing this screen would ever write. */
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

describe('the links field a candidate submits', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('convener.token', 'tok');
  });

  it('never puts an unsafe scheme in a raw href', async () => {
    const s = double({ id: 'spk-links', links: ['javascript:alert(document.cookie)'] });
    vi.stubGlobal('fetch', backend([s]));
    show(s);
    await screen.findByText('javascript:alert(document.cookie)');
    // The text is still shown -- a board member reviewing the proposal
    // must see exactly what was submitted -- but nothing on the page may
    // carry it as a clickable href.
    const anchors = document.querySelectorAll('a[href^="javascript:"]');
    expect(anchors).toHaveLength(0);
    vi.unstubAllGlobals();
  });

  it('still renders an ordinary http(s) link as a real, clickable href', async () => {
    const s = double({ id: 'spk-links-2', links: ['https://example.org/talk'] });
    vi.stubGlobal('fetch', backend([s]));
    show(s);
    const link = await screen.findByRole('link', { name: 'https://example.org/talk' });
    expect(link).toHaveAttribute('href', 'https://example.org/talk');
    vi.unstubAllGlobals();
  });
});
