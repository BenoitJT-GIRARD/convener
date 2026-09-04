import { parisToday } from '../state/derived';
import { canArchive, standingObjections } from '../state/governance';
import { RETENTION_WINDOW_DAYS, destructionDue } from '../state/retention';
import type { Config, Speaker } from '../data/types';

/**
 * What a record that has left the working board reports.
 *
 * **A closed record reports; it does not ask.** The page used to answer the
 * other way round on an archived event: it drew the publication gate -- the
 * speaker's consent as a pair of radio buttons, the board's approval, an
 * objection box, an *Approve again* -- on a record whose whole meaning is
 * that those were settled. Either the question is open and the event is
 * `delivered`, or it is settled and the event is `archived`; the page was
 * saying both at once, and the incoherence was logical rather than cosmetic.
 *
 * So the gate went back to `delivered`, which is the only status it can
 * honestly be drawn on (`state/transitions.ts::canTransition`), and this took
 * its place. The objection that kept it there for so long was that removing
 * the controls would leave an empty page. It does not: what was decided, why,
 * and what is still ahead is a page of its own.
 *
 * The other three closed statuses are here rather than in a second component
 * because they are the same question asked four times -- *why is this closed,
 * when, and what could reopen it* -- and an answer written in two places is
 * two answers waiting to disagree. Each one is drawn from the fields the
 * record actually carries, and where it carries none, this says so: a page
 * that guessed a day nobody wrote down would be worse than one that admits
 * the record is silent.
 *
 * **Nothing here is a control.** The one that reopens each of them --
 * *Reactivate* for a parked or board-declined lead, *Reopen the publication
 * decision* for an archived event -- is drawn by `ActionButtons`, which is
 * where every status's own closing controls are drawn and where
 * `pipeline-and-manual.test.ts` looks for them.
 *
 * And two things it deliberately does not carry. The message that tells
 * people the recording is up is a text to copy rather than anything about
 * the record, so it sits beside this rather than inside it -- see
 * `screens/SpeakerPage.tsx`, which is where every other content block on
 * this page is composed. The attendance figures and the ballots are not
 * restated either: `screens/SpeakerPage.tsx::SpeakerDetails` reports both, on this
 * same page, a few lines below -- one notion, one home
 * (`docs/engineering/content-rules.md`, section 7).
 */
export function ClosedRecord({ speaker, config }: { speaker: Speaker; config: Config | null }) {
  const today = parisToday();
  const p = speaker.publication;
  const archived = speaker.status === 'archived';
  const published = p.outcome === 'published';
  // Only ever asked of a record that says it published something. It is the
  // one contradiction a file hand-edited outside this application can still
  // produce, and a report that showed it in silence would be no report.
  const wrong = archived && published && config ? !canArchive(speaker, config, today).allowed : false;
  const due = destructionDue(speaker.date);

  return (
    <section className="border border-border p-4 space-y-4">
      <div>
        <h2 className="font-display font-extrabold text-xs uppercase tracking-[0.16em] text-ink">
          {TITLES[speaker.status] ?? 'How this record closed'}
        </h2>
        <p className="text-sm mt-1">{whyLine(speaker)}</p>
      </div>

      {wrong && (
        <p className="p-3 border-l-2 border-danger bg-danger/5 text-sm text-danger">
          <strong>This recording is online and should not be.</strong> Take it down, then
          reopen the record and record what changed.
        </p>
      )}

      {archived && published && speaker.youtube_url && (
        <p className="text-sm break-all">
          <a
            href={speaker.youtube_url}
            target="_blank"
            rel="noreferrer"
            className="text-field-text underline"
          >
            {speaker.youtube_url}
          </a>
        </p>
      )}

      {archived && p.objections.length > 0 && (
        <div>
          <p className="font-display font-bold uppercase tracking-widest text-[11px] text-ink-muted mb-1">
            {standingObjections(p).length > 0 ? 'Objections, one still open' : 'Objections, all closed'}
          </p>
          <ul className="text-sm space-y-1">
            {p.objections.map(o => (
              <li key={`${o.member}-${o.date}`}>
                <strong>{o.member}</strong> on {o.date}: {o.reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      {archived && (
        <div>
          <p className="font-display font-bold uppercase tracking-widest text-[11px] text-ink-muted mb-1">
            Participants&apos; personal data
          </p>
          <p className="text-sm">{retentionLine(due, today)}</p>
        </div>
      )}

      <div>
        <p className="font-display font-bold uppercase tracking-widest text-[11px] text-ink-muted mb-1">
          What could reopen it
        </p>
        <p className="text-sm">{reopenLine(speaker)}</p>
      </div>
    </section>
  );
}

/** The heading each closed status reads under. A record with no entry here
 *  has no business on this component and gets a heading that says only that
 *  it is closed. */
const TITLES: Partial<Record<Speaker['status'], string>> = {
  archived: 'How this event closed',
  parked: 'Why this lead is parked',
  'decline-board': 'Why the board declined this lead',
  'decline-speaker': 'Why this invitation ended here',
};

/** Why the record is closed, in one sentence, from the fields it carries. */
function whyLine(s: Speaker): string {
  switch (s.status) {
    case 'archived':
      return outcomeLine(s);
    case 'parked':
      return (
        'The board set this lead aside rather than deciding it. That is not a refusal, and ' +
        `${when(s, 'the day it was parked is not on the record')} The ballots and any notes are below.`
      );
    case 'decline-board':
      return (
        'The board voted and this lead did not reach the bar. ' +
        `${when(s, 'the record does not carry the day')} The ballots, with any reasons given, are below.`
      );
    case 'decline-speaker':
      return (
        'The speaker turned down the invitation. Which evenings were offered is on the ' +
        'record; the day they answered is not, because nothing writes one down.'
      );
    default:
      return 'This record has left the working board.';
  }
}

/** The day the vote closed, as a sentence, or `absent` where none is on the
 *  record. Never a guess: the parking and the two declines each write a
 *  status and nothing else, so the vote's own day is the only day there is. */
function when(s: Speaker, absent: string): string {
  return s.selection.decided_on
    ? `the vote closed on ${s.selection.decided_on}.`
    : `${absent}.`;
}

/** What became of the recording, and why. Read off the record's own fields
 *  rather than from `canArchive`, whose sentences point a volunteer at
 *  controls ("resolve this below") that a closed record does not carry. */
function outcomeLine(s: Speaker): string {
  const p = s.publication;
  if (p.outcome === 'published') {
    // What the record says about the speaker, never what the outcome
    // implies about them: a published outcome beside a refused consent is a
    // shape a hand edit can still write, and the banner above says so. A
    // sentence that read the agreement off the outcome would put words in a
    // researcher's mouth on the one subject this gate exists to protect.
    const said =
      p.consent === 'granted'
        ? 'The speaker agreed'
        : p.consent === 'refused'
          ? 'The speaker refused'
          : 'The speaker was never recorded as answering';
    return (
      `The recording is published. ${said}, and ${p.approved_by || 'a board member'} ` +
      `approved it on ${p.approved_on || 'a day the record does not give'}.`
    );
  }
  if (p.outcome === 'withheld') {
    return 'The recording is not published: the board resolved to withhold it, and only the board can lift that.';
  }
  if (p.consent === 'refused') {
    return 'The recording is not published: the speaker did not agree to it going online.';
  }
  if (p.consent === 'granted') {
    return 'The recording is not published, though the speaker agreed — either the board never approved it, or an objection took it down.';
  }
  return 'The recording is not published: the speaker was never asked, or never answered.';
}

/** When this event's registrations stop being readable, in the tense the day
 *  makes true. */
function retentionLine(due: string | null, today: string): string {
  if (!due) {
    return `This record carries no day of the talk, so there is no day ${RETENTION_WINDOW_DAYS} days after it to name.`;
  }
  const tense = today >= due ? 'was due to be destroyed on' : 'is due to be destroyed on';
  return (
    `The key that reads this event's registrations ${tense} ${due}, the talk plus ` +
    `${RETENTION_WINDOW_DAYS} days. Whether it has actually gone is recorded in the ` +
    'repository and not on this screen, which never reads that register.'
  );
}

/** What could open the record again, named as the control that does it. */
function reopenLine(s: Speaker): string {
  switch (s.status) {
    case 'archived':
      return (
        'If the speaker changes their mind, or the board does, Reopen the publication decision ' +
        'puts this record back to delivered, where the two permissions are recorded. It changes ' +
        'nothing else, and only a board member can press it.'
      );
    case 'parked':
    case 'decline-board':
      return (
        'Reactivate puts this back among the leads, with the ballots it already carries. ' +
        'Only a board member can press it.'
      );
    case 'decline-speaker':
      return (
        'Nothing here. The speaker removed themselves, and there is no board decision left to ' +
        'undo; a speaker who becomes free later starts again as a new lead.'
      );
    default:
      return 'Nothing on this page.';
  }
}
