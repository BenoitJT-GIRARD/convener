/**
 * How the programme is composed (G-13).
 *
 * This screen is where a careful measure can become a careless impression. A
 * board member reads it for fifteen seconds and leaves with one sentence, so
 * the three ways `src/state/diversity.ts` can be thrown away are all closed
 * here by what the screen *cannot* draw, not by what it checks:
 *
 * 1. **A `too-few` share is never a zero.** The screen never sees one. It
 *    reads `reportOn`, whose `too-few` arm carries no buckets at all, so
 *    there is no row, no bar and no zero to misread -- only a sentence saying
 *    how many people told us and how many are needed.
 * 2. **No percentage is computed here.** There is not a single division in
 *    this file. A share is printed as the count and the denominator it was
 *    taken against ("4 of 12 who told us"), which is the only form the state
 *    layer produces, and bars are absent because a bar's width *is* a
 *    percentage.
 * 3. **One dimension at a time.** Career stage beside country, row for row,
 *    hands the reader the cross-tabulation `diversity.ts` refused to compute:
 *    over thirty speakers, "the postdoc in Portugal" is one named person. The
 *    picker selects a single dimension and the other two leave the page, so
 *    the intersection cannot be read off the layout. There is no filter, for
 *    the same reason -- a filter is a cross-tabulation with extra steps.
 *
 * Applicants and those selected are shown side by side, over one window, both
 * dated by `selection.opened_on`: without the applicant denominator, a
 * selection bias and a sourcing bias look identical. Nothing here writes, and
 * nothing here blocks -- the policy guides the board's judgement, it does not
 * exercise it.
 */
import { useState } from 'react';
import { useData } from '../data/DataContext';
import { LoadError } from '../components/LoadError';
import { parisToday } from '../state/derived';
import { MIN_REPORTING_BASIS, distribution, reportOn } from '../state/diversity';
import type { Counts, DimensionReport, Distribution } from '../state/diversity';
import type { CareerStage, Gender } from '../data/types';

const CAREER_STAGE_LABEL: Record<CareerStage, string> = {
  phd: 'PhD student',
  postdoc: 'Postdoc',
  independent: 'Independent researcher',
  'group-leader': 'Group leader',
  other: 'Other',
  undisclosed: 'Not declared',
};

const GENDER_LABEL: Record<Gender, string> = {
  M: 'Man',
  F: 'Woman',
  NB: 'Non-binary',
  undisclosed: 'Not declared',
};

/**
 * The two natures of objective, which must never be merged (G-13).
 *
 * A stated preference is a deliberate, published bias the board applies on
 * purpose. A balance target is indicative, bounded to the window, and nobody
 * is held to it. Merging them would turn a published editorial choice into an
 * unstated quota, or an indicative target into a rule -- both are worse than
 * either, so the nature is a property of the dimension and is printed beside
 * every one of them.
 */
type Nature = 'preference' | 'target';

const NATURE_LABEL: Record<Nature, string> = {
  preference: 'Stated preference',
  target: 'Balance target',
};

const NATURE_NOTE: Record<Nature, string> = {
  preference:
    'A deliberate, published bias. The series favours emerging and less-visible ' +
    'researchers — a genuine preference, not a hard rule: established names are ' +
    'welcome, they simply should not crowd out the rest.',
  target:
    'Indicative only, and bounded to the window below. Left alone a line-up drifts ' +
    'senior and male, so the board watches this on purpose — but nothing here is a ' +
    'quota, and no figure on this screen is a pass mark.',
};

interface Dimension {
  key: string;
  label: string;
  nature: Nature;
  /** The attribute in the sentence the screen writes when it cannot report. */
  noun: string;
  report: (counts: Counts) => DimensionReport<string>;
  bucket: (key: string) => string;
}

const DIMENSIONS: Dimension[] = [
  {
    key: 'career_stage',
    label: 'Career stage',
    nature: 'preference',
    noun: 'career stage',
    report: c => reportOn(c.career_stage),
    bucket: k => CAREER_STAGE_LABEL[k as CareerStage] ?? k,
  },
  {
    key: 'gender',
    label: 'Gender',
    nature: 'target',
    noun: 'gender',
    report: c => reportOn(c.gender),
    bucket: k => GENDER_LABEL[k as Gender] ?? k,
  },
  {
    key: 'country',
    label: 'Country',
    nature: 'target',
    noun: 'country',
    report: c => reportOn(c.country),
    bucket: k => k,
  },
];

interface Population {
  heading: string;
  /** Plural noun for the people counted, used in the sentences below. */
  noun: string;
  empty: string;
  counts: (d: Distribution) => Counts;
}

const POPULATIONS: Population[] = [
  {
    heading: 'Applicants',
    noun: 'applicants',
    empty: 'No lead in this window, so there is nothing to measure.',
    counts: d => d.applicants,
  },
  {
    heading: 'Selected',
    noun: 'speakers selected',
    empty: 'No speaker in this window has been selected yet, so there is nothing to measure.',
    counts: d => d.selected,
  },
];

function speakersPhrase(n: number): string {
  return n === 1 ? '1 speaker carries' : `${n} speakers carry`;
}

/** One population, one dimension. Every arm of the report has its own shape;
 *  none of them is another arm with a number blanked out. */
function Panel({
  population,
  dimension,
  report,
}: {
  population: Population;
  dimension: Dimension;
  report: DimensionReport<string>;
}) {
  return (
    <section className="border border-border p-4">
      <h2 className="font-display font-extrabold text-xs uppercase tracking-[0.16em] mb-3">
        {population.heading}
      </h2>

      {report.kind === 'empty' && <p className="text-sm text-ink-muted">{population.empty}</p>}

      {report.kind === 'too-few' && (
        <p className="text-sm text-ink-muted">
          Not enough declared answers to report a share: {MIN_REPORTING_BASIS} are needed, and{' '}
          {report.declared} of the {report.total} {population.noun} in this window have told us
          their {dimension.noun}. What you are looking at is missing data, not a programme measured
          at zero.
        </p>
      )}

      {report.kind === 'reportable' && (
        <>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs uppercase tracking-wider text-ink-muted text-left">
                <th className="py-2 font-medium">{dimension.label}</th>
                <th className="py-2 font-medium">Of those who told us</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border border-y border-border">
              {report.rows.map(row => (
                <tr key={row.key}>
                  <td className="py-2">{dimension.bucket(row.key)}</td>
                  <td className="py-2 font-mono text-xs">
                    {row.share.count} of {row.share.of} who told us
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-xs text-ink-muted">
            {report.undisclosed} of the {report.total} {population.noun} in this window did not
            declare a {dimension.noun}. They are counted in the total and left out of every
            denominator above.
          </p>
        </>
      )}
    </section>
  );
}

/**
 * The measure itself, given a window already computed.
 *
 * Split from `Diversity` so the reading of the figures can be tested against
 * a fixed window and a fixed day, with no clock and no network in the way.
 */
export function DistributionView({ dist }: { dist: Distribution }) {
  const [dimensionKey, setDimensionKey] = useState(DIMENSIONS[0].key);
  const dimension = DIMENSIONS.find(d => d.key === dimensionKey) ?? DIMENSIONS[0];

  return (
    <div>
      <div className="mb-8">
        <p className="text-xs font-bold tracking-[0.14em] uppercase text-accent mb-2 flex items-center gap-3">
          <span className="h-0.5 bg-accent w-8" />
          How the programme is composed
        </p>
        <h1 className="font-display font-extrabold text-3xl uppercase tracking-tight">Diversity</h1>
      </div>

      <p className="text-sm text-ink-muted mb-2">
        Sliding window: {dist.from} to {dist.to}, both days included. Applicants and those selected
        are dated the same way, by the day the lead was opened, so the two columns describe the same
        set of people.
      </p>
      <p className="text-sm text-ink-muted mb-6">
        {speakersPhrase(dist.undated)} no application date and{' '}
        {dist.undated === 1 ? 'is' : 'are'} counted in neither column. This screen records no
        decision and blocks nothing: the policy guides the board&rsquo;s judgement, it does not
        exercise it.
      </p>

      <div className="mb-6 border-t border-border pt-6 space-y-4">
        {(['preference', 'target'] as Nature[]).map(nature => (
          <div key={nature} className="flex flex-wrap items-baseline gap-3">
            <span
              className={`text-xs font-bold uppercase tracking-[0.14em] shrink-0 ${
                nature === 'preference' ? 'text-accent' : 'text-ink-muted'
              }`}
            >
              {NATURE_LABEL[nature]}
            </span>
            <span className="flex gap-2">
              {DIMENSIONS.filter(d => d.nature === nature).map(d => (
                <button
                  key={d.key}
                  type="button"
                  onClick={() => setDimensionKey(d.key)}
                  className={`px-3 py-1 text-sm border transition-colors ${
                    d.key === dimension.key
                      ? 'border-primary text-primary'
                      : 'border-border text-ink-muted hover:text-ink'
                  }`}
                >
                  {d.label}
                </button>
              ))}
            </span>
            <span className="basis-full text-xs text-ink-muted">{NATURE_NOTE[nature]}</span>
          </div>
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-2 mb-6">
        {POPULATIONS.map(population => (
          <Panel
            key={population.heading}
            population={population}
            dimension={dimension}
            report={dimension.report(population.counts(dist))}
          />
        ))}
      </div>

      <p className="text-xs text-ink-muted">
        One dimension at a time, by design. Career stage set beside country, row for row, would let
        a reader reconstruct a single named person out of an aggregate — which is why the measure
        behind this screen counts each dimension on its own and never crosses two.
      </p>
    </div>
  );
}

export function Diversity() {
  const { config, speakers, loading, error } = useData();

  if (loading) return <p className="text-ink-muted">Loading…</p>;
  if (error) return <LoadError message={error} />;
  if (!config) return <p className="text-ink-muted">Nothing to show yet.</p>;

  return (
    <DistributionView
      dist={distribution(speakers, config.balance_window_months, parisToday())}
    />
  );
}
