import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../src/auth/AuthContext';
import { DataProvider } from '../src/data/DataContext';
import { Diversity, DistributionView } from '../src/screens/Diversity';
import { TopTabs } from '../src/components/TopTabs';
import { distribution } from '../src/state/diversity';
import { serializeConfig, serializeSpeakers } from '../src/data/yaml';
import { parisToday } from '../src/state/derived';
import { speaker as double } from './data-doubles';
import type { CareerStage, Config, Gender, Speaker } from '../src/data/types';

const TODAY = '2026-08-18';
const WINDOW = 24;

/** A lead opened today, from the shared double. `opened_on` is what puts it
 *  inside the reporting window, and it is the one field this screen needs
 *  set on every record. */
function speaker(id: string, overrides: Partial<Speaker> = {}): Speaker {
  return double({
    id,
    name: id,
    selection: { ballots: [], opened_on: TODAY, decided_on: '' },
    ...overrides,
  });
}

/** The repository as it stands today: everyone `undisclosed` on both declared
 *  attributes, so every share the state layer will produce is `too-few`. */
function allUndisclosed(n: number, undated = 0): Speaker[] {
  const rows = Array.from({ length: n }, (_, i) => speaker(`s${i}`));
  for (let i = 0; i < undated; i++) rows[i].selection.opened_on = '';
  return rows;
}

/** A window with enough declared answers that shares are reportable. */
function declared(stages: CareerStage[], genders: Gender[] = []): Speaker[] {
  return stages.map((stage, i) =>
    speaker(`d${i}`, { career_stage: stage, gender: genders[i] ?? 'undisclosed', country: 'UK' }),
  );
}

function view(speakers: Speaker[]) {
  return render(
    <MemoryRouter>
      <DistributionView dist={distribution(speakers, WINDOW, TODAY)} />
    </MemoryRouter>,
  );
}

function bodyText(): string {
  return document.body.textContent ?? '';
}

describe('Diversity screen', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('names the two natures of objective with different labels', () => {
    view(allUndisclosed(24));
    const preference = screen.getByText('Stated preference');
    const target = screen.getByText('Balance target');
    expect(preference).toBeInTheDocument();
    expect(target).toBeInTheDocument();
    expect(preference.textContent).not.toBe(target.textContent);
  });

  it('shows applicants and those selected side by side on one window', () => {
    view(declared(Array<CareerStage>(12).fill('postdoc')));
    expect(screen.getByRole('heading', { name: 'Applicants' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Selected' })).toBeInTheDocument();
    expect(bodyText()).toContain('2024-08-18');
    expect(bodyText()).toContain(TODAY);
  });

  it('disables no control, whatever the distribution shows', () => {
    view(allUndisclosed(24));
    expect(document.querySelectorAll('button:disabled')).toHaveLength(0);
    expect(document.querySelectorAll('[aria-disabled="true"]')).toHaveLength(0);
    expect(bodyText()).toContain('blocks nothing');
  });

  // The central guarantee. Below the reporting basis there are no buckets on
  // screen at all -- not a bucket showing zero, not an empty bar. A reader
  // cannot mistake absence of data for a measured zero because there is
  // nothing bucket-shaped to read.
  it('renders no bucket at all when the basis is too few, rather than a row of zeros', () => {
    view(allUndisclosed(24));
    expect(screen.queryByText('Postdoc')).not.toBeInTheDocument();
    expect(screen.queryByText('PhD student')).not.toBeInTheDocument();
    expect(screen.queryByText('Group leader')).not.toBeInTheDocument();
    expect(screen.queryAllByRole('row')).toHaveLength(0);
    expect(bodyText()).toContain('Not enough declared answers to report a share');
    expect(bodyText()).toContain('missing data, not a programme measured at zero');
  });

  it('says how many told us, and how many are needed, instead of showing a number', () => {
    view(allUndisclosed(24));
    expect(bodyText()).toContain('0 of the 24 applicants in this window have told us');
    expect(bodyText()).toContain('10 are needed');
  });

  it('never prints a percentage, on either the reportable or the unreportable path', () => {
    view(allUndisclosed(24));
    expect(bodyText()).not.toContain('%');
    view(declared(Array<CareerStage>(12).fill('postdoc')));
    expect(bodyText()).not.toContain('%');
  });

  it('reports a share as a count and its declared denominator once the basis holds', () => {
    const stages: CareerStage[] = [
      ...Array<CareerStage>(8).fill('postdoc'),
      ...Array<CareerStage>(4).fill('phd'),
    ];
    view(declared(stages));
    expect(screen.getByText('Postdoc')).toBeInTheDocument();
    expect(bodyText()).toContain('8 of 12 who told us');
    expect(bodyText()).toContain('4 of 12 who told us');
  });

  it('says an empty population is empty rather than measuring it', () => {
    view(allUndisclosed(24));
    expect(bodyText()).toContain('No speaker in this window has been selected yet');
  });

  it('captions the speakers it could not place in the window', () => {
    view(allUndisclosed(31, 7));
    expect(bodyText()).toContain('7 speakers carry no application date');
  });

  // Task 17 refused to compute intersections because over ~30 speakers an
  // intersection names one person. A screen that puts two dimensions on
  // screen together, row for row, hands the reader the same intersection.
  it('shows one dimension at a time, so no cross-tabulation can be read off it', () => {
    const stages: CareerStage[] = Array<CareerStage>(12).fill('postdoc');
    view(declared(stages));
    expect(screen.getByText('Postdoc')).toBeInTheDocument();
    expect(screen.queryByText('UK')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Country' }));
    expect(screen.getAllByText('UK').length).toBeGreaterThan(0);
    expect(screen.queryByText('Postdoc')).not.toBeInTheDocument();
  });

  it('offers the board a route to it', () => {
    render(
      <MemoryRouter>
        <TopTabs />
      </MemoryRouter>,
    );
    const link = screen.getByRole('link', { name: 'Diversity' });
    expect(link).toHaveAttribute('href', '/diversity');
  });

  it('renders from the loaded repository data', async () => {
    // Dated from the real clock so the window always contains them, whatever
    // day the suite runs on -- the wrapper asks `parisToday()`, not TODAY.
    const speakers = allUndisclosed(24);
    for (const s of speakers) s.selection.opened_on = parisToday();
    const config: Config = {
      season: 2026, vw_counter: 1, overlap_window_days: 7, seminar_duration_minutes: 90,
      board: [{ login: 'alice', joined_on: '2024-01-01', status: 'active', unavailable_until: '' }],
      nominations: [], board_min: 3, board_max: 9, vote_window_days: 10,
      objection_window_working_days: 3, inactivity_months: 6, balance_window_months: WINDOW,
      view_count_window_days: 30,
      sla_days: {
        lead_decision: 14, invitation_follow_up: 7,
        summary_after_delivery: 5, recording_after_delivery: 10,
      },
      channels: [],
    };
    const encode = (text: string) => {
      const bytes = new TextEncoder().encode(text);
      let bin = '';
      for (const b of bytes) bin += String.fromCharCode(b);
      return btoa(bin);
    };
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.includes('/user')) {
          return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
        }
        if (url.includes('config.yml')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ content: encode(serializeConfig(config)), sha: 'cfg-0' }),
          });
        }
        if (url.includes('speakers.yml')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ content: encode(serializeSpeakers(speakers)), sha: 'spk-0' }),
          });
        }
        return Promise.resolve({ ok: false, status: 404, text: async () => 'no' });
      }),
    );
    localStorage.setItem('convener.token', 'tok');
    render(
      <MemoryRouter>
        <AuthProvider>
          <DataProvider>
            <Diversity />
          </DataProvider>
        </AuthProvider>
      </MemoryRouter>,
    );
    expect(await screen.findByRole('heading', { name: 'Applicants' })).toBeInTheDocument();
    expect(bodyText()).toContain('Not enough declared answers to report a share');
    expect(bodyText()).not.toContain('%');
  });
});
