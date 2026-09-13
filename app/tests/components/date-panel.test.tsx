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
import { editionCodePrefix, editionNumber, nextEditionCode } from '../../src/state/agenda';
import type { Speaker } from '../../src/data/types';

/** The board double with prose in it, which is what a real `config.yml` is:
 *  on the shipped example, 27 comment lines carrying the arbitration behind
 *  every value. A write of this file used to replace all of it with a
 *  one-line constant. */
const BOARD_YAML = [
  '# Editorial Board, the season, and the thresholds a vote is measured against.',
  '# Written by whoever stood this instance up; nothing upstream rewrites it.',
  boardYaml(['alice', 'bob', 'carol', 'dan']).trimEnd(),
  '',
].join('\n');

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
function makeBackend(
  initial: Speaker[],
  /** Somebody else's commit, landing between this UI's read and its write.
   *  Called once, just before the first `speakers.yml` PUT is judged, and
   *  whatever it returns becomes the file on the server under a fresh sha --
   *  so the PUT meets 409 and `mutate` replays its transformation against
   *  this list. It is the only way to exercise the replay from the outside,
   *  and the replay is where an edition code is now decided. */
  interleave?: (current: Speaker[]) => Speaker[],
) {
  let server = initial;
  let sha = 'sha-0';
  let counter = 0;
  let interleaved = false;
  const configWrites: string[] = [];

  const fetchMock = vi.fn((url: string, opts?: RequestInit) => {
    if (url.includes('/user')) {
      return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
    }
    if (url.includes('speakers.yml')) {
      if (opts?.method === 'PUT') {
        const body = JSON.parse(opts.body as string);
        if (interleave && !interleaved) {
          interleaved = true;
          server = interleave(server);
          sha = `sha-${++counter}`;
        }
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
    if (opts?.method === 'PUT') {
      const body = JSON.parse(opts.body as string);
      configWrites.push(decodeUtf8(body.content));
      return Promise.resolve({ ok: true, json: async () => ({ content: { sha: 'cfgsha2' } }) });
    }
    return Promise.resolve({
      ok: true,
      json: async () => ({ content: encodeUtf8(BOARD_YAML), sha: 'cfgsha' }),
    });
  });

  return {
    fetchMock,
    current: () => server,
    /** The bytes of every configuration file this UI sent, in order. The
     *  edition counter lives there and nowhere else, so a reading about it
     *  cannot come from `speakers.yml`. */
    configWrites,
  };
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
function confirmed(
  candidate_dates: Speaker['candidate_dates'],
  overrides: Partial<Speaker> = {},
): Speaker {
  return speaker({
    id: 'spk-001',
    name: 'Confirmed One',
    status: 'confirmed',
    title: 'A talk',
    abstract: 'About something',
    // A record ready to lock carries a way into the room, because locking is
    // what opens registration. `BOARD_YAML` above has no series
    // `instructions`, so this is the only source here -- which is the shape
    // of an instance that opens a room per seminar.
    zoom_link: 'https://example.test/room/spk-001',
    candidate_dates,
    ...overrides,
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

  it('raises the edition counter past the code it just assigned', async () => {
    // The defect, measured on a live instance: the cockpit assigned that
    // instance's first edition, `next_edition_number` stayed at 1, and
    // `sh gates.sh` went red -- over a key no screen exposes, one moment
    // after this screen reported success. Nothing in either language wrote
    // the counter; every one of the five places it appears read it.
    const s = confirmed([{ date: '2027-03-16', time: '20:30', answer: 'accepted' }]);
    const backend = makeBackend([s]);
    renderFor(s, 'lock', backend);

    await waitFor(() => {
      fireEvent.click(screen.getByRole('button', { name: 'Suggest the next code' }));
      expect(screen.getByRole('button', { name: /Lock this date/ })).not.toBeDisabled();
    });
    fireEvent.click(screen.getByRole('button', { name: /Lock this date/ }));

    await waitFor(() => expect(backend.current()[0].status).toBe('scheduled'));
    const assigned = backend.current()[0].edition_code;
    const expected = (editionNumber(assigned) ?? 0) + 1;

    await waitFor(() => expect(backend.configWrites).toHaveLength(1));
    expect(backend.configWrites[0]).toContain(`next_edition_number: ${expected}`);

    // And the file it wrote is still the file it read. This is the wiring
    // `data/config-write.ts` is read on its own for: the defect was never in
    // a helper nobody called, it was in the one line of `DataContext` that
    // chose to parse and re-serialise. Measured on a live instance, this very
    // write took config.yml from 31 comment lines to 1.
    for (const line of BOARD_YAML.split('\n').filter(l => l.startsWith('#'))) {
      expect(backend.configWrites[0], line).toContain(line);
    }
  });

  it('will not lock a date until there is a way into the room', async () => {
    // The panel's own wiring, not the rule underneath it. `BOARD_YAML` here
    // declares no series `instructions`, so this is an instance that opens a
    // room per seminar -- and a record with no link of its own has nowhere
    // to send the first person who registers, which locking is what allows.
    const s = confirmed([{ date: '2027-03-16', time: '20:30', answer: 'accepted' }], {
      zoom_link: '',
    });
    const backend = makeBackend([s]);
    renderFor(s, 'lock', backend);

    // The edition first, so the only thing still missing is the room and the
    // reading below cannot pass for the wrong reason.
    await waitFor(() => {
      fireEvent.click(screen.getByRole('button', { name: 'Suggest the next code' }));
      const box = screen.getByPlaceholderText(`${editionCodePrefix()}N`) as HTMLInputElement;
      expect(box.value).not.toBe('');
    });
    expect(screen.getByText(/^A way into the room/)).toBeTruthy();
    expect(screen.getByRole('button', { name: /Lock this date/ })).toBeDisabled();

    // And typing one in the box clears it, in the same write -- the link is
    // carried in the lock-in's own payload rather than saved separately.
    fireEvent.change(screen.getByPlaceholderText('https://…'), {
      target: { value: 'https://example.test/room/typed' },
    });
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Lock this date/ })).not.toBeDisabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: /Lock this date/ }));

    await waitFor(() => expect(backend.current()[0].status).toBe('scheduled'));
    expect(backend.current()[0].zoom_link).toBe('https://example.test/room/typed');
  });

  it('decides a suggested code against the records the write lands on', async () => {
    // The defect. `Suggest the next code` reads the agenda as it was when the
    // button was pressed. Two volunteers locking a date at the same moment
    // were each handed the same next code and each wrote it, and nothing
    // refuses a duplicate `edition_code` until `validate-data.yml` fails on a
    // commit that is already pushed -- a red instance and a repair by hand,
    // for a product whose whole claim is that no volunteer has to understand
    // git.
    //
    // Here the other volunteer's record lands between this panel's read and
    // its write, carrying the very code this panel is about to use.
    const s = confirmed([{ date: '2027-03-16', time: '20:30', answer: 'accepted' }]);
    let taken = '';
    const backend = makeBackend([s], current => {
      // Whatever the panel is about to suggest is what the other volunteer
      // has just used, read off the same function rather than spelled again.
      taken = nextEditionCode(current, 1);
      return [
        ...current,
        speaker({ id: 'spk-999', status: 'scheduled', edition_code: taken }),
      ];
    });
    renderFor(s, 'lock', backend);

    await waitFor(() => {
      fireEvent.click(screen.getByRole('button', { name: 'Suggest the next code' }));
      expect(screen.getByRole('button', { name: /Lock this date/ })).not.toBeDisabled();
    });
    fireEvent.click(screen.getByRole('button', { name: /Lock this date/ }));

    await waitFor(() => {
      const mine = backend.current().find(r => r.id === s.id);
      expect(mine?.status).toBe('scheduled');
    });
    const mine = backend.current().find(r => r.id === s.id);

    expect(taken).not.toBe('');
    expect(mine?.edition_code).not.toBe(taken);
    expect(
      backend.current().filter(r => r.edition_code === taken),
    ).toHaveLength(1);
  });

  it('writes a code the volunteer typed exactly as typed, replay or not', async () => {
    // The other direction, and it is not symmetry for its own sake. Typing a
    // code is a decision -- renumbering a series, matching a poster already
    // printed -- and a panel that quietly substituted its own reading would
    // write something other than what the screen said, which is the one thing
    // this whole change exists to stop.
    const s = confirmed([{ date: '2027-03-16', time: '20:30', answer: 'accepted' }]);
    const backend = makeBackend([s], current => [
      ...current,
      speaker({ id: 'spk-999', status: 'scheduled', edition_code: nextEditionCode(current, 1) }),
    ]);
    renderFor(s, 'lock', backend);

    const typed = `${editionCodePrefix()}77`;
    await waitFor(() => {
      fireEvent.change(screen.getByPlaceholderText(`${editionCodePrefix()}N`), {
        target: { value: typed },
      });
      expect(screen.getByRole('button', { name: /Lock this date/ })).not.toBeDisabled();
    });
    fireEvent.click(screen.getByRole('button', { name: /Lock this date/ }));

    await waitFor(() => {
      const mine = backend.current().find(r => r.id === s.id);
      expect(mine?.status).toBe('scheduled');
    });
    expect(backend.current().find(r => r.id === s.id)?.edition_code).toBe(typed);
  });

  it('raises the counter from the code it wrote, not the one it offered', async () => {
    // The two halves have to agree. After a replay the code on screen and the
    // code in the commit differ, and a counter raised from the screen would
    // leave the mark below an edition that exists -- the very state the
    // counter was added to prevent, reintroduced by the fix for a different
    // defect.
    const s = confirmed([{ date: '2027-03-16', time: '20:30', answer: 'accepted' }]);
    const backend = makeBackend([s], current => [
      ...current,
      speaker({ id: 'spk-999', status: 'scheduled', edition_code: nextEditionCode(current, 1) }),
    ]);
    renderFor(s, 'lock', backend);

    await waitFor(() => {
      fireEvent.click(screen.getByRole('button', { name: 'Suggest the next code' }));
      expect(screen.getByRole('button', { name: /Lock this date/ })).not.toBeDisabled();
    });
    fireEvent.click(screen.getByRole('button', { name: /Lock this date/ }));

    await waitFor(() => expect(backend.configWrites).toHaveLength(1));
    const written = backend.current().find(r => r.id === s.id)?.edition_code ?? '';
    const expected = (editionNumber(written) ?? 0) + 1;

    expect(backend.configWrites[0]).toContain(`next_edition_number: ${expected}`);
  });

  it('writes the record before the counter, so a failure lags rather than burns a number', async () => {
    // Order, not decoration. These are two files with no transaction
    // between them, so one order has to be chosen and defended.
    //
    // A counter raised first, with the record then failing, leaves a number
    // burnt and no record carrying it. A record written first, with the
    // counter then failing, leaves the mark lagging -- loud in `sh gates.sh`,
    // and harmless while that record stands, because `nextEditionCode` skips
    // every code already in use. The lag is only reachable at all once
    // somebody clears the row too, which is itself a deliberate act taken
    // past a red gate.
    const s = confirmed([{ date: '2027-03-16', time: '20:30', answer: 'accepted' }]);
    const backend = makeBackend([s]);
    renderFor(s, 'lock', backend);

    await waitFor(() => {
      fireEvent.click(screen.getByRole('button', { name: 'Suggest the next code' }));
      expect(screen.getByRole('button', { name: /Lock this date/ })).not.toBeDisabled();
    });
    fireEvent.click(screen.getByRole('button', { name: /Lock this date/ }));

    await waitFor(() => expect(backend.configWrites).toHaveLength(1));
    expect(backend.current()[0].status).toBe('scheduled');
  });
});
