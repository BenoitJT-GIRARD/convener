import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../src/auth/AuthContext';
import { DataProvider } from '../src/data/DataContext';
import { Board } from '../src/screens/Board';
import { parseConfig, serializeConfig } from '../src/data/yaml';
import { speaker as double } from './data-doubles';
import type { BoardMember, Config, Nomination, Speaker } from '../src/data/types';

function member(login: string, overrides: Partial<BoardMember> = {}): BoardMember {
  return { login, joined_on: '2024-01-01', status: 'active', unavailable_until: '', ...overrides };
}

function config(overrides: Partial<Config> = {}): Config {
  return {
    season: 2026,
    next_edition_number: 1,
    overlap_window_days: 7,
    seminar_duration_minutes: 90,
    eligibility_share: 0.6666666666666666,
    board: [member('alice'), member('bob'), member('carol')],
    nominations: [],
    board_min: 3,
    board_max: 9,
    vote_window_days: 10,
    objection_window_working_days: 3,
    inactivity_months: 6,
    balance_window_months: 12,
    view_count_window_days: 30,
    sla_days: {
      invitation_follow_up: 7,
      summary_after_delivery: 5,
      recording_after_delivery: 10,
    },
    channels: [],
    instructions: '',
    ...overrides,
  };
}

/** A delivered seminar hosted by `host` -- the only two facts this screen
 *  reads off a speaker. Everything else comes from the shared double. */
function speaker(id: string, host: string): Speaker {
  return double({ id, name: id, host_1: host, status: 'delivered' });
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

/** A stand-in for the Contents API that enforces the sha precondition on
 *  config.yml, like the real one, so a stale write is rejected once. */
function makeBackend(initial: Config, speakers: Speaker[]) {
  let server = initial;
  let sha = 'cfg-0';
  let counter = 0;

  const fetchMock = vi.fn((url: string, opts?: RequestInit) => {
    if (url.includes('/user')) {
      return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
    }
    if (url.includes('config.yml')) {
      if (opts?.method === 'PUT') {
        const body = JSON.parse(opts.body as string);
        if (body.sha !== sha) {
          return Promise.resolve({ ok: false, status: 409, text: async () => 'stale sha' });
        }
        server = parseConfig(decodeUtf8(body.content)) as Config;
        sha = `cfg-${++counter}`;
        return Promise.resolve({ ok: true, json: async () => ({ content: { sha } }) });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ content: encodeUtf8(serializeConfig(server)), sha }),
      });
    }
    // speakers.yml, and the team-membership lookup role.ts makes.
    if (url.includes('speakers.yml')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({
          content: encodeUtf8(JSON.stringify(speakers)),
          sha: 'spk-0',
        }),
      });
    }
    return Promise.resolve({ ok: false, status: 404, text: async () => 'no' });
  });

  return {
    fetchMock,
    /** Another member's write landing straight on the remote, behind this
     *  component's back. */
    interlope(next: Config) {
      server = next;
      sha = `cfg-other-${++counter}`;
    },
    current: () => server,
  };
}

function renderBoard(backend: { fetchMock: ReturnType<typeof vi.fn> }) {
  vi.stubGlobal('fetch', backend.fetchMock);
  render(
    <MemoryRouter>
      <AuthProvider>
        <DataProvider>
          <Board />
        </DataProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('Board screen', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    localStorage.setItem('convener.token', 'tok');
  });

  it('lists every member with status and availability', async () => {
    const cfg = config({
      board: [member('alice'), member('bob', { unavailable_until: '2099-01-01' }), member('carol', { status: 'inactive' })],
    });
    renderBoard(makeBackend(cfg, []));

    expect(await screen.findByText('away until 2099-01-01')).toBeInTheDocument();
    expect(screen.getAllByText('available')).toHaveLength(1);
    expect(screen.getByText('inactive')).toBeInTheDocument();
  });

  it('reports the board against its target, and reports it either way', async () => {
    // `board_min` is enforced nowhere -- see `state/board.ts` -- so the
    // screen is one of the two places it is said out loud. Said only when
    // the board is short of it, the number would be invisible on every
    // healthy board and unlearnable from the screen.
    renderBoard(makeBackend(config({ board_min: 3, board_max: 9 }), []));
    expect(
      await screen.findByText('3 active members. The board aims for 3 and seats at most 9.'),
    ).toBeInTheDocument();
  });

  it('says a board under its target is under it, and that nothing is blocked', async () => {
    const cfg = config({
      board: [member('alice'), member('bob'), member('carol', { status: 'inactive' })],
      board_min: 5,
    });
    renderBoard(makeBackend(cfg, []));

    // Active members, not entries: the inactive row holds no seat, which is
    // the same count the validator reports on.
    const note = await screen.findByText(/2 active members, below the board's target of 5/);
    expect(note.textContent).toContain('Nothing is blocked by that');
  });

  it('declares an absence for yourself against a freshly-read config', async () => {
    const backend = makeBackend(config(), []);
    renderBoard(backend);

    const field = await screen.findByLabelText('Away until');
    fireEvent.change(field, { target: { value: '2099-02-01' } });

    // Someone else adds a member between this component's read and its
    // write. A transform that used the `config` from render would drop
    // them; one that reads `current` keeps them.
    backend.interlope(config({ board: [member('alice'), member('bob'), member('carol'), member('dan')] }));

    fireEvent.click(screen.getByRole('button', { name: 'Save absence' }));
    await waitFor(() =>
      expect(backend.current().board.find(m => m.login === 'alice')?.unavailable_until).toBe(
        '2099-02-01',
      ),
    );
    expect(backend.current().board.map(m => m.login)).toEqual(['alice', 'bob', 'carol', 'dan']);

    // F-16. `unavailable_until` is read by `activeBoard`, so an absence
    // moves `N` and with it the majority a speaker needs: it is a decision,
    // and its subject comes out of `formatDecision` like every other one.
    // It used to be the free prose `data: mark alice unavailable until ...`,
    // which `parse_decision` could not read back, so the register lost it.
    const subject = (backend.fetchMock.mock.calls
      .filter(([, opts]) => (opts as RequestInit | undefined)?.method === 'PUT')
      .map(([, opts]) => JSON.parse((opts as RequestInit).body as string).message as string))[0];
    expect(subject).toBe('data: record the availability of alice by alice (away)');
  });

  it('records coming back as the same act, with the other value', async () => {
    const backend = makeBackend(
      config({ board: [member('alice', { unavailable_until: '2099-02-01' }), member('bob')] }),
      [],
    );
    renderBoard(backend);

    // The field starts empty, and an empty field is the way back: the
    // control says so rather than needing a second act.
    fireEvent.click(await screen.findByRole('button', { name: 'Mark me available' }));
    await waitFor(() =>
      expect(backend.current().board.find(m => m.login === 'alice')?.unavailable_until).toBe(''),
    );

    const subject = (backend.fetchMock.mock.calls
      .filter(([, opts]) => (opts as RequestInit | undefined)?.method === 'PUT')
      .map(([, opts]) => JSON.parse((opts as RequestInit).body as string).message as string))[0];
    expect(subject).toBe('data: record the availability of alice by alice (back)');
  });

  it('keeps the nomination control disabled and says why, rather than failing on submit', async () => {
    const backend = makeBackend(config(), [speaker('spk-001', 'dan')]);
    renderBoard(backend);

    const field = await screen.findByLabelText('Nominate');
    fireEvent.change(field, { target: { value: 'dan' } });

    expect(await screen.findByText(/has co-hosted 1 webinar/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open nomination' })).toBeDisabled();
  });

  it('opens a nomination for an eligible candidate', async () => {
    const backend = makeBackend(config(), [speaker('spk-001', 'dan'), speaker('spk-002', 'dan')]);
    renderBoard(backend);

    const field = await screen.findByLabelText('Nominate');
    fireEvent.change(field, { target: { value: 'dan' } });
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Open nomination' })).not.toBeDisabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Open nomination' }));

    await waitFor(() => expect(backend.current().nominations).toHaveLength(1));
    expect(backend.current().nominations[0]).toMatchObject({
      candidate: 'dan',
      sponsor: 'alice',
      outcome: '',
    });
  });

  it('records an objection with its reason, and defers the nomination', async () => {
    const open: Nomination = {
      candidate: 'dan',
      sponsor: 'bob',
      opened_on: '2026-03-01',
      objections: [],
      outcome: '',
    };
    const backend = makeBackend(config({ nominations: [open] }), []);
    renderBoard(backend);

    const reason = await screen.findByLabelText('Reason for objecting to dan');
    expect(screen.getByRole('button', { name: 'Object' })).toBeDisabled();
    fireEvent.change(reason, { target: { value: 'not yet' } });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Object' })).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', { name: 'Object' }));

    await waitFor(() => expect(backend.current().nominations[0].outcome).toBe('deferred'));
    expect(backend.current().nominations[0].objections).toEqual([
      { member: 'alice', reason: 'not yet', date: expect.any(String) },
    ]);
  });

  it('offers the withdrawal only to the member whose objection it is', async () => {
    // `alice` is the signed-in member here. The objection is `bob`'s, so
    // there is no control at all for her to press -- the rule and the screen
    // cannot disagree, because the screen asks the rule.
    const deferred: Nomination = {
      candidate: 'dan',
      sponsor: 'carol',
      opened_on: '2026-03-01',
      objections: [{ member: 'bob', reason: 'too soon', date: '2026-03-02' }],
      outcome: 'deferred',
    };
    const backend = makeBackend(config({ nominations: [deferred] }), []);
    renderBoard(backend);

    await screen.findByText('dan');
    expect(screen.queryByRole('button', { name: 'Withdraw my objection' })).toBeNull();
  });

  it('re-opens the nomination when the objector withdraws, and restarts the window', async () => {
    const deferred: Nomination = {
      candidate: 'dan',
      sponsor: 'carol',
      opened_on: '2026-03-01',
      objections: [{ member: 'alice', reason: 'too soon', date: '2026-03-02' }],
      outcome: 'deferred',
    };
    const backend = makeBackend(config({ nominations: [deferred] }), []);
    renderBoard(backend);

    fireEvent.click(await screen.findByRole('button', { name: 'Withdraw my objection' }));

    await waitFor(() => expect(backend.current().nominations[0].outcome).toBe(''));
    expect(backend.current().nominations[0].objections).toEqual([]);
    // The seven days run again from today, not from the original opening.
    expect(backend.current().nominations[0].opened_on).not.toBe('2026-03-01');
  });

  it('shows what is due and records it on demand', async () => {
    const due: Nomination = {
      candidate: 'dan',
      sponsor: 'bob',
      opened_on: '2020-01-01',
      objections: [],
      outcome: '',
    };
    const backend = makeBackend(config({ nominations: [due] }), []);
    renderBoard(backend);

    fireEvent.click(await screen.findByRole('button', { name: 'Record the outcome' }));
    await waitFor(() => expect(backend.current().nominations[0].outcome).toBe('accepted'));
    expect(backend.current().board.some(m => m.login === 'dan' && m.status === 'active')).toBe(true);
  });

  it('offers no write to someone who is not on the board', async () => {
    const backend = makeBackend(config({ board: [member('bob'), member('carol')] }), []);
    renderBoard(backend);

    expect(await screen.findByText('bob')).toBeInTheDocument();
    expect(screen.queryByLabelText('Nominate')).toBeNull();
    expect(screen.queryByLabelText('Away until')).toBeNull();
  });

  it('records who joined the board, one register row per nomination', async () => {
    // G-12 makes board entry a registrable decision. A single row saying the
    // nominations were applied records that the board changed without
    // recording who joined it, and a commit subject is the only place that
    // survives.
    const nomination = (candidate: string): Nomination => ({
      candidate,
      sponsor: 'alice',
      opened_on: '2020-01-01',
      objections: [],
      outcome: '',
    });
    const backend = makeBackend(
      config({ nominations: [nomination('dan'), nomination('erin')] }),
      [],
    );
    renderBoard(backend);

    fireEvent.click(await screen.findByRole('button', { name: 'Record the outcome' }));

    await waitFor(() =>
      expect(backend.current().board.map(m => m.login)).toEqual([
        'alice',
        'bob',
        'carol',
        'dan',
        'erin',
      ]),
    );

    const subjects = backend.fetchMock.mock.calls
      .filter(([, opts]) => (opts as RequestInit | undefined)?.method === 'PUT')
      .map(([, opts]) => JSON.parse((opts as RequestInit).body as string).message as string);
    expect(subjects).toEqual([
      'data: settle the nomination of dan by alice',
      'data: settle the nomination of erin by alice',
    ]);
  });
});
