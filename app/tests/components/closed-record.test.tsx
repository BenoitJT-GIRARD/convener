import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ClosedRecord } from '../../src/components/ClosedRecord';
import { SPEAKER_STATUSES } from '../../src/data/validate';
import { AGENDA_STATUSES, BOARD_STATUSES } from '../../src/state/agenda';
import { RETENTION_WINDOW_DAYS } from '../../src/state/retention';
import type { Config, Publication, Speaker, SpeakerStatus } from '../../src/data/types';
import { speaker as double } from '../helpers/data-doubles';

/**
 * The report a closed record shows in place of the controls it used to
 * carry.
 *
 * The archived case is the one R63 is about, and the three others are the
 * ones it asked to be checked alongside: a page that says why a record is
 * closed but not what would open it again leaves a volunteer with a status
 * and no move.
 */

function config(): Config {
  return {
    season: 2026,
    next_edition_number: 6,
    overlap_window_days: 7,
    seminar_duration_minutes: 90,
    eligibility_share: 0.6666666666666666,
    board: [{ login: 'alice', joined_on: '2020-01-01', status: 'active', unavailable_until: '' }],
    nominations: [],
    board_min: 3,
    board_max: 9,
    vote_window_days: 14,
    objection_window_working_days: 3,
    inactivity_months: 6,
    balance_window_months: 12,
    view_count_window_days: 30,
    sla_days: { invitation_follow_up: 7, summary_after_delivery: 5, recording_after_delivery: 10 },
    channels: [],
    instructions: '',
  };
}

function publication(overrides: Partial<Publication> = {}): Publication {
  return { consent: 'pending', approved_by: '', approved_on: '', objections: [], outcome: '', ...overrides };
}

function closed(status: SpeakerStatus, overrides: Partial<Speaker> = {}): Speaker {
  return double({ id: 'spk-001', name: 'Ada Lovelace', status, date: '2026-03-12', ...overrides });
}

function show(s: Speaker) {
  render(<ClosedRecord speaker={s} config={config()} />);
}

describe('an archived event reports what was decided', () => {
  it('says the recording is published, who approved it and when, and links it', () => {
    show(
      closed('archived', {
        youtube_url: 'https://video.example.test/watch/mrg-1',
        publication: publication({
          consent: 'granted',
          approved_by: 'alice',
          approved_on: '2026-03-20',
          outcome: 'published',
        }),
      }),
    );
    expect(screen.getByText(/The recording is published/)).toBeInTheDocument();
    expect(screen.getByText(/The speaker agreed, and alice approved it on 2026-03-20/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'https://video.example.test/watch/mrg-1' })).toBeInTheDocument();
  });

  it('never reads the speaker’s agreement off the outcome', () => {
    // A published outcome beside a refused consent is a shape a hand edit
    // can still write, and the one thing this page must not do with it is
    // report an agreement nobody gave.
    show(
      closed('archived', {
        publication: publication({
          consent: 'refused',
          approved_by: 'alice',
          approved_on: '2026-03-20',
          outcome: 'published',
        }),
      }),
    );
    expect(screen.getByText(/The speaker refused, and alice approved it/)).toBeInTheDocument();
    expect(screen.getByText(/This recording is online and should not be/)).toBeInTheDocument();
  });

  it('separates a board that withheld from a speaker who refused', () => {
    show(closed('archived', { publication: publication({ consent: 'granted', outcome: 'withheld' }) }));
    expect(screen.getByText(/the board resolved to withhold it/)).toBeInTheDocument();

    screen.getByText(/the board resolved to withhold it/).remove();
    show(closed('archived', { publication: publication({ consent: 'refused' }) }));
    expect(screen.getByText(/the speaker did not agree to it going online/)).toBeInTheDocument();
  });

  it('names the day the registrations stop being readable, and does not claim they have', () => {
    show(closed('archived', { date: '2026-03-12', publication: publication({ consent: 'granted' }) }));
    // 2026-03-12 plus ninety days.
    const line = screen.getByText(/registrations/);
    expect(line.textContent).toContain('2026-06-10');
    expect(line.textContent).toContain(`${RETENTION_WINDOW_DAYS} days`);
    expect(line.textContent).toMatch(/never reads that register/);
  });

  it('says so rather than naming a day, when the record carries no date', () => {
    show(closed('archived', { date: '', publication: publication({ consent: 'granted' }) }));
    expect(screen.getByText(/carries no day of the talk/)).toBeInTheDocument();
  });

  it('offers a door rather than the gate', () => {
    show(closed('archived', { publication: publication({ consent: 'granted', outcome: 'published' }) }));
    expect(screen.getByText(/Reopen the publication decision/)).toBeInTheDocument();
    // The report is a report: none of the gate's own controls is on it.
    expect(screen.queryByRole('radio')).toBeNull();
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.queryByRole('textbox')).toBeNull();
  });
});

describe('the three other closed statuses say why, when, and what would reopen them', () => {
  const cases: [SpeakerStatus, RegExp, RegExp][] = [
    ['parked', /set this lead aside/, /Reactivate/],
    ['decline-board', /did not reach the bar/, /Reactivate/],
    ['decline-speaker', /turned down the invitation/, /starts again as a new lead/],
  ];

  it.each(cases)('%s', (status, why, reopen) => {
    show(closed(status, { selection: { ballots: [], opened_on: '2026-01-05', decided_on: '2026-01-19' } }));
    expect(screen.getByText(why)).toBeInTheDocument();
    expect(screen.getByText(reopen)).toBeInTheDocument();
  });

  it('gives the vote’s own day where the record has one, and admits it where it does not', () => {
    show(closed('parked', { selection: { ballots: [], opened_on: '2026-01-05', decided_on: '2026-01-19' } }));
    expect(screen.getByText(/the vote closed on 2026-01-19/)).toBeInTheDocument();

    render(
      <ClosedRecord
        speaker={closed('parked', { selection: { ballots: [], opened_on: '2026-01-05', decided_on: '' } })}
        config={config()}
      />,
    );
    expect(screen.getByText(/the day it was parked is not on the record/)).toBeInTheDocument();
  });
});

describe('every status this page can be drawn on has something to say', () => {
  it('covers each of them, and no working status reaches it', () => {
    // The five the speaker page draws it for: the ones with no phase of
    // their own. A status added to the model lands here or on the board,
    // and this is what refuses a sixth arriving with no words written for
    // it -- `cancelled` was the fifth, and this line is where it had to be
    // decided rather than inherited.
    const closedStatuses = SPEAKER_STATUSES.filter(
      status => !BOARD_STATUSES.includes(status) && !AGENDA_STATUSES.includes(status),
    );
    expect([...closedStatuses].sort()).toEqual(
      ['archived', 'cancelled', 'decline-board', 'decline-speaker', 'parked'].sort(),
    );
    for (const status of closedStatuses) {
      const { unmount } = render(<ClosedRecord speaker={closed(status)} config={config()} />);
      expect(screen.getByRole('heading').textContent, status).not.toBe('How this record closed');
      expect(screen.getByText(/What could reopen it/), status).toBeInTheDocument();
      unmount();
    }
  });
});
