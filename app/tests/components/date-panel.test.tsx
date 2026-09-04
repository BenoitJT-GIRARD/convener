/**
 * The date negotiation, at the three points of the journey it appears.
 *
 * These ran against `ActionButtons` until the panel moved into the journey's
 * own sequence (`state/phases.ts`), which is what the reorder is: the dates
 * used to sit in a block above the whole checklist, so a volunteer was asked
 * to mark an invitation sent before the app would let them choose the dates
 * it names. Three new facts are asserted alongside the old ones -- that the
 * panel is offered on an approved record at all, that clicking an evening on
 * an invited one is both the acceptance and the choice, and that a further
 * evening can still be offered while the invitation is out.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { boardYaml, speaker } from '../helpers/data-doubles';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../../src/auth/AuthContext';
import { DataProvider } from '../../src/data/DataContext';
import { DatePanel, type DateMode } from '../../src/components/DatePanel';
import { parseSpeakers, serializeSpeakers } from '../../src/data/yaml';
import type { Speaker } from '../../src/data/types';

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

function renderFor(record: Speaker, mode: DateMode, backend: { fetchMock: unknown }) {
  vi.stubGlobal('fetch', backend.fetchMock);
  render(
    <MemoryRouter>
      <AuthProvider>
        <DataProvider>
          <DatePanel speaker={record} role="board" mode={mode} />
        </DataProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

/** A record at the status the lock-in belongs to, with the talk details in:
 *  `dates.lockBlockers` asks for those alongside the edition number. */
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

describe('locking a date', () => {
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
    renderFor(s, 'lock', makeBackend([s]));

    const locks = await screen.findAllByRole('button', { name: /Lock this date/ });
    expect(locks).toHaveLength(1);
    expect(screen.getByText('2027-03-16 20:30')).toBeInTheDocument();
  });

  it('names the edition number as what is still missing, and stars it', async () => {
    // R36: the button was already disabled for this reason and nothing on
    // the page said so, so the maintainer hunted for it.
    const s = confirmed([{ date: '2027-03-16', time: '20:30', answer: 'accepted' }]);
    renderFor(s, 'lock', makeBackend([s]));

    expect(await screen.findByRole('button', { name: /Lock this date/ })).toBeDisabled();
    expect(screen.getByText(/Edition — still to fill in/)).toBeInTheDocument();
  });

  it('locks the accepted slot with its own hour', async () => {
    const s = confirmed([
      { date: '2027-03-09', time: '18:00', answer: 'declined' },
      { date: '2027-03-16', time: '20:30', answer: 'accepted' },
    ]);
    const backend = makeBackend([s]);
    renderFor(s, 'lock', backend);

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

  it('offers no further evening once a date is being locked', async () => {
    // Everything on offer has been answered by now, and the question at this
    // status is which of the accepted evenings to freeze.
    const s = confirmed([{ date: '2027-03-16', time: '20:30', answer: 'accepted' }]);
    renderFor(s, 'lock', makeBackend([s]));
    await screen.findByRole('button', { name: /Lock this date/ });
    expect(screen.queryByLabelText('Offer date')).toBeNull();
  });
});

describe('offering the evenings the invitation names', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    localStorage.setItem('convener.token', 'tok');
  });

  /** An approved record: the board has said yes, the invitation is being
   *  prepared, and nobody has been asked anything yet. */
  function approved(candidate_dates: Speaker['candidate_dates'] = []): Speaker {
    return speaker({ id: 'spk-001', name: 'Approved One', status: 'approved', candidate_dates });
  }

  it('lets a date be offered before the invitation is marked sent', async () => {
    // The defect this reorder answers (R34): the panel was not on this
    // status at all, so the dates the invitation names could only be chosen
    // after somebody had said the invitation had gone.
    const s = approved();
    const backend = makeBackend([s]);
    renderFor(s, 'offer', backend);

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
    // Nobody has been asked yet, so there is nothing to reply for them.
    expect(screen.queryByRole('button', { name: /They can make this one/ })).toBeNull();
  });

  it('refuses a clashing date at the offer, naming the event in the way', async () => {
    const s = approved();
    const other = speaker({
      id: 'spk-009',
      name: 'Other One',
      status: 'scheduled',
      date: '2027-03-18',
      time: '18:00',
      edition_code: 'MRG-09',
    });
    renderFor(s, 'offer', makeBackend([s, other]));

    fireEvent.change(await screen.findByLabelText('Offer date'), {
      target: { value: '2027-03-16' },
    });

    expect(await screen.findByText(/clashes with MRG-09/)).toBeInTheDocument();
    // Read before clicking, not after a failed save.
    expect(screen.getByRole('button', { name: 'Offer this date' })).toBeDisabled();
  });

  it('shows an offered evening as part of the invitation, not as a silence', async () => {
    const s = approved([{ date: '2027-03-16', time: '18:00', answer: '' }]);
    renderFor(s, 'offer', makeBackend([s]));
    expect(await screen.findByText('in the invitation')).toBeInTheDocument();
    expect(screen.queryByText('no reply yet')).toBeNull();
  });
});

describe('what the speaker replies while the invitation is out', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    localStorage.setItem('convener.token', 'tok');
  });

  function invited(candidate_dates: Speaker['candidate_dates']): Speaker {
    return speaker({ id: 'spk-001', name: 'Invited One', status: 'invited', candidate_dates });
  }

  it('takes one click for both the acceptance and the evening', async () => {
    // R35: a global *Speaker accepted* beside a per-date *they accepted* was
    // two gestures for one fact, and either could be recorded without the
    // other. The click on the evening is now both.
    const s = invited([
      { date: '2027-03-09', time: '18:00', answer: '' },
      { date: '2027-03-16', time: '18:00', answer: '' },
    ]);
    const backend = makeBackend([s]);
    renderFor(s, 'reply', backend);

    const accepts = await screen.findAllByRole('button', { name: /They can make this one/ });
    await waitFor(() => expect(accepts[1]).not.toBeDisabled());
    fireEvent.click(accepts[1]);

    await waitFor(() => expect(backend.current()[0].status).toBe('confirmed'));
    expect(backend.current()[0].candidate_dates.map(c => c.answer)).toEqual(['', 'accepted']);
  });

  it('records an evening they cannot make without moving the record', async () => {
    const s = invited([{ date: '2027-03-09', time: '18:00', answer: '' }]);
    const backend = makeBackend([s]);
    renderFor(s, 'reply', backend);

    const no = await screen.findByRole('button', { name: 'not this one' });
    await waitFor(() => expect(no).not.toBeDisabled());
    fireEvent.click(no);

    await waitFor(() =>
      expect(backend.current()[0].candidate_dates[0].answer).toBe('declined'),
    );
    expect(backend.current()[0].status).toBe('invited');
  });

  it('lets a further evening be offered without writing to anybody', async () => {
    // The real case the maintainer names: the speaker can make none of the
    // three and proposes a fourth. Offering it used to mean going back to a
    // status the record had left.
    const s = invited([
      { date: '2027-03-02', time: '18:00', answer: 'declined' },
      { date: '2027-03-09', time: '18:00', answer: 'declined' },
      { date: '2027-03-16', time: '18:00', answer: 'declined' },
    ]);
    const backend = makeBackend([s]);
    renderFor(s, 'reply', backend);

    fireEvent.change(await screen.findByLabelText('Offer date'), {
      target: { value: '2027-03-23' },
    });
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Offer this date' })).not.toBeDisabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Offer this date' }));

    await waitFor(() => expect(backend.current()[0].candidate_dates).toHaveLength(4));
    // The three refusals stay: re-offering never quietly erases an answer.
    expect(backend.current()[0].candidate_dates.map(c => c.answer)).toEqual([
      'declined',
      'declined',
      'declined',
      '',
    ]);
  });
});
