import { describe, it, expect, vi, beforeEach } from 'vitest';
import { boardYaml, speaker } from '../helpers/data-doubles';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../../src/auth/AuthContext';
import { DataProvider } from '../../src/data/DataContext';
import { ActionButtons } from '../../src/components/ActionButtons';
import { parseSpeakers, serializeSpeakers } from '../../src/data/yaml';
import type { Ballot, BallotValue, Speaker } from '../../src/data/types';

function ballot(voter: string, value: BallotValue = 'yes'): Ballot {
  return { voter, value, comment: '', coi_reason: '', date: '2026-05-20' };
}

/** A lead with its vote open, built from the shared double rather than from
 *  a copy of the model: a field added to `Speaker` reaches this file on its
 *  own, instead of leaving it describing a record the reader now refuses. */
function lead(ballots: Ballot[] = []): Speaker {
  return speaker({
    name: 'Lead One',
    selection: { ballots, opened_on: '2026-05-01', decided_on: '' },
  });
}

/** Four active members, so `thresholdFor(4)` is 3 yes votes. */
const BOARD_YAML = boardYaml(['alice', 'bob', 'carol', 'dan']);

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

/** A stand-in for the GitHub Contents API that enforces the sha precondition,
 *  so a write goes through the same path the real one does. */
function makeBackend(initial: Speaker[]) {
  let server = initial;
  let sha = 'sha-0';
  let counter = 0;

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
    return Promise.resolve({
      ok: true,
      json: async () => ({ content: encodeUtf8(BOARD_YAML), sha: 'cfgsha' }),
    });
  });

  return { fetchMock, current: () => server };
}

function renderFor(speaker: Speaker, backend: { fetchMock: unknown }) {
  vi.stubGlobal('fetch', backend.fetchMock);
  render(
    <MemoryRouter>
      <AuthProvider>
        <DataProvider>
          <ActionButtons speaker={speaker} role="board" />
        </DataProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

/** The board arrives with config.yml, and every control stays disabled until
 *  it does -- so a test that clicks before then would click a no-op. */
async function waitForBoard() {
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Submit ballot' })).not.toBeDisabled(),
  );
}

describe('ActionButtons ballot form', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    localStorage.setItem('convener.token', 'tok');
  });

  it('offers all three ballot values, not just yes', async () => {
    // `abstain` and `recused` are the two values that move the denominator.
    // A UI that only offers "yes" makes the recusal rule unusable.
    const speaker = lead();
    renderFor(speaker, makeBackend([speaker]));

    expect(await screen.findByRole('radio', { name: /Yes/ })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /Abstain/ })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /Recuse myself/ })).toBeInTheDocument();
  });

  it('asks for the recusal reason up front instead of rejecting the save', async () => {
    const speaker = lead();
    const backend = makeBackend([speaker]);
    renderFor(speaker, backend);

    await waitForBoard();
    fireEvent.click(screen.getByRole('radio', { name: /Recuse myself/ }));

    expect(screen.getByRole('button', { name: 'Submit ballot' })).toBeDisabled();
    expect(screen.getByText(/Required: a recusal changes/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Reason for the conflict of interest/), {
      target: { value: 'former co-author' },
    });

    const submit = screen.getByRole('button', { name: 'Submit ballot' });
    expect(submit).not.toBeDisabled();
    fireEvent.click(submit);

    await waitFor(() => expect(backend.current()[0].selection.ballots).toHaveLength(1));
    const written = backend.current()[0].selection.ballots[0];
    expect(written.value).toBe('recused');
    expect(written.coi_reason).toBe('former co-author');
  });

  it('records an abstention as such, and it does not decide the vote', async () => {
    const speaker = lead([ballot('bob'), ballot('carol')]);
    const backend = makeBackend([speaker]);
    renderFor(speaker, backend);

    await waitForBoard();
    fireEvent.click(screen.getByRole('radio', { name: /Abstain/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Submit ballot' }));

    await waitFor(() => expect(backend.current()[0].selection.ballots).toHaveLength(3));
    expect(backend.current()[0].selection.ballots[2].value).toBe('abstain');
    // Two yes out of four eligible: the bar is three, and an abstention does
    // not lower it.
    expect(backend.current()[0].status).toBe('lead');
  });

  it('decides the vote inside the write, from the board and the ballots at write time', async () => {
    const speaker = lead([ballot('bob'), ballot('carol')]);
    const backend = makeBackend([speaker]);
    renderFor(speaker, backend);

    await waitForBoard();
    fireEvent.click(screen.getByRole('button', { name: 'Submit ballot' }));

    await waitFor(() => expect(backend.current()[0].status).toBe('approved'));
    expect(backend.current()[0].selection.ballots).toHaveLength(3);
    expect(backend.current()[0].selection.decided_on).not.toBe('');
  });
});

/** A speaker whose invitation has been accepted, with the slots put to them
 *  and whatever they have replied so far. */
function confirmed(candidate_dates: Speaker['candidate_dates']): Speaker {
  return speaker({
    id: 'spk-001',
    name: 'Confirmed One',
    status: 'confirmed',
    title: 'A talk',
    abstract: 'About something',
    candidate_dates,
  });
}

describe('ActionButtons date negotiation', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    localStorage.setItem('convener.token', 'tok');
  });

  it('offers to lock only the slots the speaker accepted', async () => {
    // The one thing this panel exists to prevent: a volunteer committing an
    // unpaid outside researcher to an evening they never agreed to. There is
    // no field to type a date into, and the two slots without an acceptance
    // carry no lock button at all.
    const s = confirmed([
      { date: '2027-03-02', time: '18:00', answer: '' },
      { date: '2027-03-09', time: '18:00', answer: 'declined' },
      { date: '2027-03-16', time: '20:30', answer: 'accepted' },
    ]);
    renderFor(s, makeBackend([s]));

    const locks = await screen.findAllByRole('button', { name: /Lock this date/ });
    expect(locks).toHaveLength(1);
    expect(screen.getByText('2027-03-16 20:30')).toBeInTheDocument();
  });

  it('locks the accepted slot with its own hour', async () => {
    const s = confirmed([
      { date: '2027-03-09', time: '18:00', answer: 'declined' },
      { date: '2027-03-16', time: '20:30', answer: 'accepted' },
    ]);
    const backend = makeBackend([s]);
    renderFor(s, backend);

    // Disabled until the edition number is there: a rule the volunteer can
    // satisfy disables the control instead of failing the save.
    expect(await screen.findByRole('button', { name: /Lock this date/ })).toBeDisabled();
    await waitFor(() => {
      fireEvent.click(screen.getByRole('button', { name: 'Suggest the next code' }));
      expect(screen.getByRole('button', { name: /Lock this date/ })).not.toBeDisabled();
    });
    fireEvent.click(screen.getByRole('button', { name: /Lock this date/ }));

    await waitFor(() => expect(backend.current()[0].status).toBe('scheduled'));
    expect(backend.current()[0].date).toBe('2027-03-16');
    expect(backend.current()[0].time).toBe('20:30');
    // The offer and the replies survive the lock-in: which dates were put to
    // the speaker is the record of how this one was chosen.
    expect(backend.current()[0].candidate_dates).toHaveLength(2);
  });

  it('refuses a clashing date at the offer, naming the event in the way', async () => {
    const s = confirmed([]);
    const other = speaker({
      id: 'spk-009',
      name: 'Other One',
      status: 'scheduled',
      date: '2027-03-18',
      time: '18:00',
      edition_code: 'MRG-09',
    });
    renderFor(s, makeBackend([s, other]));

    fireEvent.change(await screen.findByLabelText('Offer date'), {
      target: { value: '2027-03-16' },
    });

    expect(await screen.findByText(/clashes with MRG-09/)).toBeInTheDocument();
    // Read before clicking, not after a failed save.
    expect(screen.getByRole('button', { name: 'Offer this date' })).toBeDisabled();
  });

  it('writes an offered date with no answer against it', async () => {
    const s = confirmed([]);
    const backend = makeBackend([s]);
    renderFor(s, backend);

    fireEvent.change(await screen.findByLabelText('Offer date'), {
      target: { value: '2027-03-16' },
    });
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Offer this date' })).not.toBeDisabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Offer this date' }));

    await waitFor(() => expect(backend.current()[0].candidate_dates).toHaveLength(1));
    expect(backend.current()[0].candidate_dates[0]).toEqual({
      date: '2027-03-16',
      time: '12:30',
      answer: '',
    });
    // Offering is not agreeing: nothing is lockable until the speaker replies.
    expect(screen.queryByRole('button', { name: /Lock this date/ })).toBeNull();
  });

  it('records the speaker s reply against the slot it belongs to', async () => {
    const s = confirmed([
      { date: '2027-03-09', time: '18:00', answer: '' },
      { date: '2027-03-16', time: '18:00', answer: '' },
    ]);
    const backend = makeBackend([s]);
    renderFor(s, backend);

    const accepts = await screen.findAllByRole('button', { name: 'they accepted' });
    await waitFor(() => expect(accepts[1]).not.toBeDisabled());
    fireEvent.click(accepts[1]);

    await waitFor(() =>
      expect(backend.current()[0].candidate_dates.map(c => c.answer)).toEqual(['', 'accepted']),
    );
  });
});
