/**
 * Who is on the board, who is available, and who a new lead falls to.
 *
 * `governance.ts` computes the vote threshold from the *eligible* board --
 * active members, minus those who declared an absence, minus those recused
 * on a lead. This module supplies the first two of those: `activeBoard`
 * produces the active-member logins and the subset of them unavailable on a
 * given date; `governance.eligibleVoters` does the subtracting.
 *
 * `assignLead` crosses the language boundary: `tools/convener_ops/journey/proposal.py`
 * implements the same rule for the public-form intake path, and both are
 * pinned by `tools/tests/fixtures/governance-cases.json`'s `assign_lead_cases`.
 */
import type { BoardMember, Config, Nomination, Speaker } from '../data/types';
import { isIdentifier } from './decisions';

export interface Board {
  logins: string[];
  unavailable: string[];
}

/**
 * Active board members as of `on` (ISO `YYYY-MM-DD`), and which of them
 * declared an absence covering that date.
 *
 * `unavailable_until` is inclusive: a member is still unavailable *on* that
 * date, and available again only the day after. An empty `unavailable_until`
 * means no declared absence.
 */
export function activeBoard(config: Config, on: string): Board {
  const active = config.board.filter(m => m.status === 'active');
  return {
    logins: active.map(m => m.login),
    unavailable: active.filter(m => isUnavailable(m, on)).map(m => m.login),
  };
}

function isUnavailable(member: BoardMember, on: string): boolean {
  return member.unavailable_until !== '' && member.unavailable_until >= on;
}

/** Whether `login` is an active board member as of `on` -- availability
 *  aside; an unavailable member is still a board member. */
export function isBoardMember(config: Config, login: string, on: string): boolean {
  return activeBoard(config, on).logins.includes(login);
}

/** Events `login` has actually co-hosted: `delivered` or `archived` only. A
 *  `scheduled` event has not happened yet, so it cannot yet count toward
 *  nomination eligibility. */
export function coHostedCount(speakers: Speaker[], login: string): number {
  return speakers.filter(
    s =>
      (s.host_1 === login || s.host_2 === login) &&
      (s.status === 'delivered' || s.status === 'archived'),
  ).length;
}

/** The numeric suffix of a speaker id (`spk-007` -> 7), used only as a
 *  creation-order proxy for `assignLead`'s tie-break. `-1` for anything that
 *  does not match, so an unparsable id sorts as "oldest". */
function idOrder(id: string): number {
  const m = /^spk-(\d+)/.exec(id);
  return m ? parseInt(m[1], 10) : -1;
}

/**
 * The active, available board member to whom a new lead falls:
 * whoever carries the fewest open leads (status `lead`, `assigned_to` that
 * member -- *not* `proposed_by`, which stays the submitter's self-reported
 * name and is never counted here). A tie goes to whoever's most recent open
 * lead is the oldest -- i.e. whoever has gone longest without a new one --
 * using the id's numeric suffix as a stand-in for creation order, since ids
 * are assigned in strictly increasing order (see
 * `tools/convener_ops/journey/proposal.py::to_lead`). Any further tie (including "never
 * assigned") falls back to alphabetical login order, so the result never
 * depends on `config.board`'s incidental ordering and repeated calls with
 * the same input always agree.
 *
 * Returns `''` -- never throws -- when no member is both active and
 * available: the caller displays that the assignment is pending rather than
 * surfacing a raw error to a volunteer. The caller is responsible for
 * writing the returned login into the speaker's `assigned_to` field.
 */
export function assignLead(speakers: Speaker[], config: Config, on: string): string {
  const { logins, unavailable } = activeBoard(config, on);
  const away = new Set(unavailable);
  const eligible = logins.filter(login => !away.has(login)).sort();
  if (eligible.length === 0) return '';

  const openLeadIds = new Map<string, number[]>(eligible.map(login => [login, []]));
  for (const s of speakers) {
    if (s.status !== 'lead') continue;
    const ids = openLeadIds.get(s.assigned_to);
    if (ids) ids.push(idOrder(s.id));
  }

  const keyFor = (login: string): [count: number, mostRecent: number] => {
    const ids = openLeadIds.get(login) ?? [];
    return [ids.length, ids.length === 0 ? -1 : Math.max(...ids)];
  };

  return eligible.reduce((best, login) => {
    const [bestCount, bestRecent] = keyFor(best);
    const [count, recent] = keyFor(login);
    const better = count < bestCount || (count === bestCount && recent < bestRecent);
    return better ? login : best;
  });
}

/* ------------------------------------------------------------------ *
 * Nominations (G-05)
 *
 * How the board renews itself: a Contributor who has co-hosted at least
 * two webinars is put forward by a board member, and joins when a majority
 * of the eligible board has said yes inside the window. **Silence counts as
 * refusal.** A member who has said nothing has not agreed, and no length of
 * waiting turns that into a yes -- which is why `nominationStanding` counts
 * the supports on the record rather than counting the members who have not
 * objected.
 *
 * The default used to run the other way: one sponsor, seven days, and
 * anybody the board did not actively stop was seated. One member's act plus
 * a quiet fortnight was the whole of it, which is a board a small group can
 * turn over.
 *
 * There is deliberately no rejected outcome in the vocabulary. The three
 * outcomes a transformation here can write are `accepted` (seated),
 * `deferred` (the question goes to a meeting -- either because a member
 * objected or because the window ran out below the bar) and `waiting` (the
 * board agreed and there is no seat). None of them is terminal against the
 * candidate, and none can be written by a scheduled job: `resolveNominations`
 * is called from the Board screen by a signed-in member.
 *
 * These are pure functions of their arguments, today's date included, so
 * they run inside a `mutate` transformation that may be replayed against a
 * freshly-read config after a concurrent write.
 * ------------------------------------------------------------------ */

/** Days the board has to express itself on a nomination (G-05). Calendar
 *  days, not working days: `objection_window_working_days` is the
 *  *publication* gate (G-08), a different window with a different unit. So
 *  `windowHasRun` below deliberately does *not* go through
 *  `state/working-days.ts`: that module counts the working-day windows, and
 *  routing this one through it would stretch a fortnight into three weeks --
 *  a real decision moved by real days, on nobody's authority.
 *
 *  Fourteen, and the same fourteen as `config.vote_window_days` and as the
 *  `lead_decision` turnaround target: all three are the board being asked to
 *  express itself. Seven was enough while a member only had to act to *stop*
 *  a nomination; now every one of them has to act for it to carry. */
export const NOMINATION_WINDOW_DAYS = 14;

/** Supports a nomination needs however small the board is (G-05).
 *
 *  A majority on its own gives one, on a board of two, and one member
 *  seating another is what this rule exists to prevent. It is the same
 *  three as `governance.MINIMUM_YES` and for the same reason, and it is a
 *  constant of its own rather than that one imported: they are two rules
 *  about two questions, and folding them into one number would make a
 *  change to the speaker's bar move the board's own membership with it. */
export const NOMINATION_MINIMUM_SUPPORTS = 3;

/** How many supports carry a nomination on a board of `eligible` members:
 *  more than half, and never fewer than `NOMINATION_MINIMUM_SUPPORTS`. 5 ->
 *  3 and 8 -> 5, matching the table the handbook states.
 *
 *  Deliberately not `governance.thresholdFor`: that is two thirds and it
 *  decides a speaker. This is a majority and it appoints a member. */
export function nominationBar(eligible: number): number {
  return Math.max(Math.floor(eligible / 2) + 1, NOMINATION_MINIMUM_SUPPORTS);
}

/** Webinars a candidate must have actually co-hosted to be nominated,
 *  counted from `instance/data/speakers.yml` by `coHostedCount` -- never declared in
 *  the config, never inferred from board membership. */
export const NOMINATION_MIN_CO_HOSTED = 2;

/** A nomination that cannot be recorded as asked. The message is a plain
 *  sentence a volunteer can act on; it reaches the screen as-is through
 *  `github/errors.ts`. The screens ask `nominationBlocker` /
 *  `objectionBlocker` first and keep the control disabled, so this is a
 *  backstop -- but a governance rule must never surface as "GitHub is not
 *  responding". */
export class NominationRejected extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'NominationRejected';
  }
}

/** Whether the automated path may still resolve this nomination. `deferred`
 *  and `accepted` are settled -- the first by the annual meeting, the
 *  second for good. `waiting` stays open: it says "the rule is satisfied,
 *  there is no seat", so it is re-examined every time the board changes. */
function isPending(n: Nomination): boolean {
  return n.outcome === '' || n.outcome === 'waiting';
}

/**
 * Whether the board still has this nomination in front of it.
 *
 * A narrower question than `isPending`, which asks whether the *automated*
 * path may settle it; `deferred` is settled there, because only the annual
 * meeting can move it. But a deferral is not a closed question, it is a
 * question moved to another room, and while it is open no second nomination
 * for the same candidate may be opened alongside it -- otherwise an objection
 * a member wrote in the morning is routed around by re-opening the same
 * nomination in the afternoon, and the deferral means nothing.
 *
 * A nomination is unsettled while it is pending, or while any objection
 * stands on it. "Stands" is simply "is in the list": nomination objections
 * are never marked resolved (see `data/types.ts`), and the only thing that
 * stops one standing is its author withdrawing it, which removes it. So a
 * hand-edited `deferred` carrying no objection at all is *not* unsettled --
 * there would be nothing to withdraw, and a state with no way out of it is
 * worse than the one this rule exists to prevent.
 *
 * Exported because this rule crosses the language boundary:
 * `tools/convener_ops/maintenance/sweep.py::_unsettled_candidates` asks the same question of
 * the same file, to keep a member the board is arguing about off the
 * inactivity proposal. The pair is pinned by
 * `tools/tests/fixtures/governance-cases.json`'s `unsettled_nomination_cases`,
 * read by both languages -- the Python copy mirrored `isPending` for a while,
 * and a seated member carrying a deferred nomination could be proposed
 * inactive out of the very file that recorded the objection.
 */
export function isUnsettled(n: Nomination): boolean {
  return isPending(n) || n.objections.length > 0;
}

/** Why a candidate the board is already considering cannot be nominated
 *  again, naming the members whose objections are the reason when that is
 *  what is holding it -- the volunteer has to know whom to talk to. */
function alreadyOpenBlocker(login: string, n: Nomination): string {
  if (n.objections.length === 0) return `A nomination for ${login} is already open.`;
  const who = n.objections.map(o => o.member).join(', ');
  return (
    `${login}'s nomination was deferred to the annual meeting: ${who} objected in ` +
    `writing. It cannot be opened again until that objection is withdrawn by the ` +
    `member who raised it.`
  );
}

/** Whole days from `from` to `to`, both ISO `YYYY-MM-DD`. `NaN` when either
 *  is unusable -- callers treat that as "the window has not run", so a
 *  hand-edited nomination with no opening date is never auto-accepted. */
function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(to) - Date.parse(from)) / 86400000);
}

function windowHasRun(nomination: Nomination, on: string): boolean {
  const days = daysBetween(nomination.opened_on, on);
  return !Number.isNaN(days) && days >= NOMINATION_WINDOW_DAYS;
}

/** Whether a support recorded on `date` falls inside the window. `NaN` on
 *  either side reads as outside, so a support with an unusable day, and
 *  every support on a nomination with an unusable opening day, is on the
 *  record and out of the count -- the direction that seats nobody. */
function inTime(nomination: Nomination, date: string): boolean {
  const days = daysBetween(nomination.opened_on, date);
  return !Number.isNaN(days) && days < NOMINATION_WINDOW_DAYS;
}

/** Where a nomination stands today: how many members could speak, how many
 *  of them have, and what it would take. */
export interface NominationStanding {
  /** Active members, minus those away today -- the denominator. */
  eligible: number;
  /** What `nominationBar` asks of that denominator. */
  bar: number;
  /** Supports that count today: one per eligible member, and none dated
   *  after the window closed. */
  supports: number;
  /** Whole days since the window opened, `0` when the record does not hold
   *  a day a clock could start from. */
  elapsed: number;
  /** Whether the board has said yes. */
  carried: boolean;
}

/**
 * How `nomination` stands on `on`.
 *
 * Eligibility is read the way `governance.eligibleVoters` reads it for a
 * speaker, less the recusal, which belongs to one speaker's record and has
 * no counterpart here: active members, minus anyone whose declared absence
 * covers the day. So the bar moves the instant somebody declares one, for
 * everyone looking, exactly as the two-thirds bar does.
 *
 * **A support dated after the window closed does not count.** Without that,
 * a nomination the board let run out could be carried by one click on the
 * twentieth day, and the days would be a suggestion rather than the whole
 * of the chance the board is given. There is no lower bound to match it: a
 * support recorded before `opened_on` is one that survived the restart
 * `withdrawObjection` performs, and a member who said yes said yes.
 *
 * Distinct members, not entries: a hand-edited file may name one member
 * twice, and repetition must not inflate a count that seats somebody.
 */
export function nominationStanding(
  config: Config,
  nomination: Nomination,
  on: string,
): NominationStanding {
  const { logins, unavailable } = activeBoard(config, on);
  const away = new Set(unavailable);
  const voters = new Set(logins.filter(login => !away.has(login)));
  const counted = new Set(
    nomination.supports.filter(s => voters.has(s.member) && inTime(nomination, s.date)).map(s => s.member),
  );
  const bar = nominationBar(voters.size);
  const days = daysBetween(nomination.opened_on, on);
  return {
    eligible: voters.size,
    bar,
    supports: counted.size,
    elapsed: Number.isNaN(days) ? 0 : days,
    carried: counted.size >= bar,
  };
}

/**
 * Why `candidate` cannot be nominated by `sponsor` today, as a plain
 * sentence -- or `''` when the nomination can be opened. The screen calls
 * this to disable the control *and* to say why, so a rule the volunteer
 * cannot satisfy is visible before they submit rather than as a failure
 * afterwards; `openNomination` calls it too, so the rule holds even if a
 * caller forgets to.
 *
 * Nothing here reads the headcount against `board_min`, and nothing should.
 * `board_min` is the size the board aims to be, not a permission to admit
 * anyone: a board under its target needs members more than a full one does,
 * so refusing a nomination there would forbid the one act that closes the
 * gap, and a nomination is in any case a question put to the board rather
 * than a seat taken. Room is a question for the moment of seating, where
 * `board_max` answers it (`resolveNominations`), not for the moment of
 * asking.
 */
export function nominationBlocker(
  speakers: Speaker[],
  config: Config,
  candidate: string,
  sponsor: string,
  on: string,
): string {
  const login = candidate.trim();
  if (login === '') return 'Give the GitHub username of the person being nominated.';
  // A GitHub username, not a name. Opening a nomination writes a commit
  // subject, and a commit subject is permanent: `Jane Doe (CNRS)` typed here
  // would put a real person's name into a history nothing rewrites, and the
  // register (`tools/convener_ops/governance/commit_format.py`) could not read the line back
  // either, so the decision would be lost as well as the privacy. The
  // identifier is checked here, where a sentence can be shown, rather than
  // left to `decisions.identifier` to refuse at the moment of writing.
  if (!isIdentifier(login)) {
    return (
      `"${login}" is not a GitHub username. Nominations are opened on the account ` +
      'that co-hosted the webinars, so type the username rather than the person.'
    );
  }

  if (!isBoardMember(config, sponsor, on)) {
    return 'Only an active board member can sponsor a nomination.';
  }
  if (isBoardMember(config, login, on)) {
    return `${login} is already on the board.`;
  }
  const unsettled = config.nominations.find(n => n.candidate === login && isUnsettled(n));
  if (unsettled) return alreadyOpenBlocker(login, unsettled);

  const hosted = coHostedCount(speakers, login);
  if (hosted < NOMINATION_MIN_CO_HOSTED) {
    return (
      `${login} has co-hosted ${hosted} webinar${hosted === 1 ? '' : 's'}. ` +
      `${NOMINATION_MIN_CO_HOSTED} are needed before a nomination can be opened.`
    );
  }
  return '';
}

/**
 * Open a nomination for `candidate`, sponsored by `sponsor`, on `today`.
 * Returns a new `Config`; never mutates the one it is given.
 *
 * Eligibility is computed here, from `speakers`, rather than taken as a
 * number from the caller -- passing a count would be declaring eligibility,
 * which is precisely what G-05 forbids. That is why this takes the speaker
 * list even though it writes only to `config.yml`: the two files are read
 * in the same load cycle, and co-hosting history changes far more slowly
 * than the config being transformed.
 *
 * A `deferred` nomination for the same candidate *does* block a new one for
 * as long as the objection that deferred it stands. Re-opening it is not an
 * act this function can perform on anybody's behalf: the only way back is
 * `withdrawObjection`, run by the member who objected. An older deferral
 * whose objections have all been withdrawn is kept in the list rather than
 * replaced, so the record of what was objected to stays readable next to the
 * new attempt.
 *
 * The sponsor's own support is written here, on the same day. Opening a
 * nomination is saying yes to it, and leaving that to a second click would
 * let a nomination sit at nought supports with the member who asked for it
 * among the silent -- and silence is a refusal now.
 */
export function openNomination(
  speakers: Speaker[],
  config: Config,
  candidate: string,
  sponsor: string,
  today: string,
): Config {
  const blocker = nominationBlocker(speakers, config, candidate, sponsor, today);
  if (blocker !== '') throw new NominationRejected(blocker);

  const nomination: Nomination = {
    candidate: candidate.trim(),
    sponsor,
    opened_on: today,
    supports: [{ member: sponsor, date: today }],
    objections: [],
    outcome: '',
  };
  return { ...config, nominations: [...config.nominations, nomination] };
}

/**
 * Which nomination a support for `candidate` lands on: the most recent one
 * the board is still being asked about, or `-1`.
 *
 * `outcome: ''` and nothing else. A `deferred` one is in another room, an
 * `accepted` one has its seat, and a `waiting` one has already carried --
 * more support would change none of the three, and offering the control
 * would suggest otherwise.
 */
function supportTarget(config: Config, candidate: string): number {
  return config.nominations.reduce(
    (found, n, i) => (n.candidate === candidate && n.outcome === '' ? i : found),
    -1,
  );
}

/**
 * Why `member` cannot support `candidate`'s nomination today, as a plain
 * sentence -- or `''` when they can.
 *
 * A member who has declared an absence is not refused. They are out of
 * today's count, like any other vote they are away for, and their support
 * counts again the day they are back if the window is still open: the
 * denominator and the numerator move together, which is what `activeBoard`
 * already does for the two-thirds bar.
 */
export function supportBlocker(
  config: Config,
  candidate: string,
  member: string,
  on: string,
): string {
  const index = supportTarget(config, candidate);
  if (index === -1) return `There is no open nomination for ${candidate}.`;
  if (!isBoardMember(config, member, on)) {
    return 'Only an active board member can support a nomination.';
  }
  const nomination = config.nominations[index];
  if (nomination.supports.some(s => s.member === member)) {
    return `You have already supported ${candidate}'s nomination.`;
  }
  if (windowHasRun(nomination, on)) {
    return (
      `The ${NOMINATION_WINDOW_DAYS} days the board had on ${candidate}'s nomination ` +
      'have run. A support recorded now does not count towards it, and the ' +
      'question goes to the meeting.'
    );
  }
  return '';
}

/**
 * Record `member`'s support for `candidate`'s nomination on `today`.
 *
 * One support per member, and no way to take one back: a member who has
 * changed their mind objects, which carries a written reason and defers the
 * nomination on the spot. So the only thing this can do is move a
 * nomination towards carrying, and it is a member's own named act -- there
 * is no path here a clock could take.
 *
 * Returns a new `Config`; never mutates the one it is given.
 */
export function supportNomination(
  config: Config,
  candidate: string,
  member: string,
  today: string,
): Config {
  const blocker = supportBlocker(config, candidate, member, today);
  if (blocker !== '') throw new NominationRejected(blocker);

  const target = supportTarget(config, candidate);
  const nominations = config.nominations.map((n, i): Nomination =>
    i === target ? { ...n, supports: [...n.supports, { member, date: today }] } : n,
  );
  return { ...config, nominations };
}

/**
 * Which nomination an objection to `candidate` lands on: the most recent
 * one that is not already accepted, or `-1` when there is none. An accepted
 * nomination is closed to objections -- the seat is taken, and re-opening it
 * is a departure (G-14), not an objection. A *deferred* one still takes
 * them: the annual meeting arbitrates on the whole record, so a second
 * member's reason must be recordable next to the first. Most recent, not
 * every match, because a deferred nomination can be brought back (see
 * `openNomination`) and the old entry is history, not a live question.
 */
function objectionTarget(config: Config, candidate: string): number {
  return config.nominations.reduce(
    (found, n, i) => (n.candidate === candidate && n.outcome !== 'accepted' ? i : found),
    -1,
  );
}

/** Why `member` cannot object to `candidate`'s nomination, as a plain
 *  sentence -- or `''` when the objection can be recorded. */
export function objectionBlocker(
  config: Config,
  candidate: string,
  member: string,
  reason: string,
  on: string,
): string {
  if (objectionTarget(config, candidate) === -1) {
    return `There is no open nomination for ${candidate}.`;
  }
  if (!isBoardMember(config, member, on)) {
    return 'Only an active board member can object to a nomination.';
  }
  if (reason.trim() === '') {
    return 'An objection needs a written reason. Add a short note before submitting.';
  }
  return '';
}

/**
 * Record `member`'s objection to `candidate`'s nomination and defer it, in
 * one transformation. The two are inseparable on purpose: an objection that
 * only appended to the list would leave a nomination carrying an objection
 * while still on course to carry, and the next `resolveNominations` would
 * have to catch it. There is no window in which that state exists.
 *
 * `deferred` is not a refusal. It means a meeting decides, with the
 * objection and its author on the record -- which is why a written reason
 * and an identified board member are both required. A second objection from
 * the same member replaces the first in place, keeping list order, exactly
 * as `ballots.castBallot` does.
 *
 * The objector's own support goes with it. A member cannot be counted on
 * both sides of one question, and the objection is the later act; the
 * support they had recorded is what they have just changed their mind
 * about.
 */
export function objectToNomination(
  config: Config,
  candidate: string,
  member: string,
  reason: string,
  today: string,
): Config {
  const blocker = objectionBlocker(config, candidate, member, reason, today);
  if (blocker !== '') throw new NominationRejected(blocker);

  const objection = { member, reason, date: today };
  const target = objectionTarget(config, candidate);
  const nominations = config.nominations.map((n, i): Nomination => {
    if (i !== target) return n;
    const existing = n.objections.some(o => o.member === member);
    return {
      ...n,
      supports: n.supports.filter(s => s.member !== member),
      objections: existing
        ? n.objections.map(o => (o.member === member ? objection : o))
        : [...n.objections, objection],
      outcome: 'deferred',
    };
  });
  return { ...config, nominations };
}

/**
 * Which nomination `member`'s own objection to `candidate` sits on, or `-1`.
 *
 * The most recent one carrying an objection of theirs, and never an accepted
 * one: an accepted nomination holds no standing objection (`resolveNominations`
 * cannot produce one, and `tools/convener_ops/governance/validate.py` refuses the pair in a
 * hand-edited file), so a hand-written objection on an accepted nomination
 * must not become a door back out of a seat that was granted.
 */
function withdrawalTarget(config: Config, candidate: string, member: string): number {
  return config.nominations.reduce(
    (found, n, i) =>
      n.candidate === candidate &&
      n.outcome !== 'accepted' &&
      n.objections.some(o => o.member === member)
        ? i
        : found,
    -1,
  );
}

/**
 * Why `member` cannot withdraw an objection to `candidate`'s nomination, as a
 * plain sentence -- or `''` when they can.
 *
 * One condition, and deliberately only one: they wrote the objection. Nothing
 * here asks whether they are still an active board member. A member who has
 * gone quiet and been moved to `inactive` would otherwise leave an objection
 * nobody on earth could lift, which is a worse state than the one this whole
 * rule exists to prevent -- and it would hand a member a way to make a
 * deferral permanent by stepping back.
 */
export function withdrawalBlocker(config: Config, candidate: string, member: string): string {
  if (withdrawalTarget(config, candidate, member) === -1) {
    return (
      `You have no objection on record against ${candidate}'s nomination. ` +
      'An objection is withdrawn by the member who raised it, and by nobody else.'
    );
  }
  return '';
}

/**
 * Withdraw `member`'s own objection to `candidate`'s nomination.
 *
 * This is the only transformation in the codebase that turns a `deferred`
 * nomination back into an open one, and it can only remove the caller's own
 * objection. There is no act anywhere -- no transition, no scheduled job, no
 * admin override -- that clears somebody else's, and no delay clears one
 * either. The annual meeting arbitrates through this same door: a member
 * whose objection the meeting does not uphold withdraws it. Nothing stored
 * records that a meeting took place, so nothing here can key on one; a rule
 * turning on a date nobody writes down would be a rule nobody could rely on.
 *
 * The objection is removed rather than flagged: `Objection` has no resolved
 * field (see `data/types.ts`), and the commit that records this act is where
 * the withdrawal survives -- the register adds, so the history keeps saying
 * what the objection said.
 *
 * When the last objection goes, the window starts again from `today` rather
 * than resuming from the original opening. The rest of the board was told
 * this nomination had been deferred; most of them will have stopped looking
 * at it, and a spent window would put the question straight back to a
 * meeting on the day it was re-opened.
 *
 * The supports already on the record stay on it, and `nominationStanding`
 * goes on counting them: one is dated before the new `opened_on` from that
 * moment, and there is no lower bound on the window for exactly this
 * reason. A member who said yes said yes, and somebody else's objection
 * being lifted is no reason to ask them again.
 *
 * Returns a new `Config`; never mutates the one it is given, and takes
 * `today` as an argument, so it runs inside a `mutate` transformation that
 * may be replayed against a freshly-read config.
 */
export function withdrawObjection(
  config: Config,
  candidate: string,
  member: string,
  today: string,
): Config {
  const blocker = withdrawalBlocker(config, candidate, member);
  if (blocker !== '') throw new NominationRejected(blocker);

  const target = withdrawalTarget(config, candidate, member);
  const nominations = config.nominations.map((n, i): Nomination => {
    if (i !== target) return n;
    const objections = n.objections.filter(o => o.member !== member);
    if (objections.length > 0) return { ...n, objections };
    return { ...n, objections, outcome: '', opened_on: today };
  });
  return { ...config, nominations };
}

/**
 * Seat `candidate` as of `on`, reactivating an existing entry rather than
 * adding a second one for the same login.
 *
 * Only what seating actually decides is written. An entry that is already
 * `active` is returned untouched, and a reactivated one keeps the
 * `joined_on` it has always had:
 *
 * - `joined_on` is the day the person joined the board, not the day of the
 *   most recent nomination. It is also what the inactivity rule (G-14) reads
 *   as the start of its silence window, so rewriting it restarts that clock
 *   for someone who has been on the board for years.
 * - `unavailable_until` is an absence that member declared about themselves
 *   (`declareUnavailability` refuses to write it for anyone else). Nobody
 *   else's act may clear it, and a nomination resolving is somebody else's
 *   act.
 *
 * Both used to be rewritten unconditionally, which an already-seated member
 * could reach without a hand edit: they are the candidate of an older
 * nomination whose last objection is later withdrawn, `resolveNominations`
 * runs, and their join date resets and their declared absence disappears.
 */
function seat(board: BoardMember[], candidate: string, on: string): BoardMember[] {
  const index = board.findIndex(m => m.login === candidate);
  if (index === -1) {
    return [...board, { login: candidate, joined_on: on, status: 'active', unavailable_until: '' }];
  }
  const existing = board[index];
  if (existing.status === 'active') return board;
  return board.map((m, i) => (i === index ? { ...m, status: 'active' } : m));
}

/**
 * Settle every nomination the board has finished with, and seat the members
 * that carries. Returns a new `Config`; never mutates its argument, and
 * returns a value-equal result when nothing is due, so it is safe to call
 * from a `mutate` transformation that may be replayed.
 *
 * Three answers, and the middle one is the change: a nomination the board
 * has carried is `accepted` (or `waiting`, if there is no seat); one still
 * inside its window is left alone; and one whose window has run without
 * reaching the bar is `deferred` -- **silence is a refusal**, so the days
 * running out settles the question instead of granting it.
 *
 * A `waiting` nomination is past that test and is not put to it again. The
 * board said yes; what it is waiting for is room, and re-reading the bar
 * against a board that has since shrunk would take a seat back from
 * somebody on nobody's decision.
 *
 * An acceptance and the board entry it implies are written together, so an
 * `accepted` nomination whose candidate is not on the board cannot exist. A
 * nomination is only accepted when it carries no objection, so an
 * `accepted` nomination with objections cannot exist either -- the
 * validator's cross-field check on that pair (`tools/convener_ops/governance/validate.py`)
 * is now a statement about hand-edited files, not a live defence.
 *
 * Seats are counted as they are filled, so a run that accepts several
 * nominations cannot overshoot `board_max` -- and so does a sequence of
 * single-candidate calls, because each reads the board the previous one
 * left; the ones that do not fit become
 * `waiting`, and stay in the running for the next call. Nothing here reads
 * `board_min`, whatever a given file declares it to be: `board_min` is a
 * target the tools report on -- `tools/convener_ops/governance/validate.py::board_target_report`
 * and the Composition table on the Board screen -- never a rule that admits
 * or refuses anyone. Seating is a question about room, and only a ceiling
 * can run short of room; a floor could only ever argue for seating someone
 * the board has not accepted, which no headcount is entitled to decide.
 */
export function resolveNominations(config: Config, today: string, only?: string): Config {
  let board = config.board;

  const nominations = config.nominations.map((n): Nomination => {
    // `only` settles one candidate's nomination and leaves the rest for a
    // later call. `Board.tsx` uses it to write one commit per nomination, so
    // the decision register records who joined the board rather than only
    // that some nominations were applied (G-10). Omitted, every due
    // nomination is settled at once, which is what the seat counting below
    // is written for.
    if (only !== undefined && n.candidate !== only) return n;
    if (!isPending(n)) return n;
    // A hand-edited nomination carrying an objection with no outcome: the
    // objection stands, so the nomination is deferred, never accepted.
    if (n.objections.length > 0) return { ...n, outcome: 'deferred' };

    // Against the board this run is building rather than the one it was
    // handed: a call that has already seated somebody has changed the
    // denominator, and the next nomination is counted over the board as it
    // now stands.
    const carried = n.outcome === 'waiting' || nominationStanding({ ...config, board }, n, today).carried;
    if (!carried) {
      if (!windowHasRun(n, today)) return n;
      return { ...n, outcome: 'deferred' };
    }

    const seated = board.some(m => m.login === n.candidate && m.status === 'active');
    const active = board.filter(m => m.status === 'active').length;
    if (!seated && active >= config.board_max) {
      return n.outcome === 'waiting' ? n : { ...n, outcome: 'waiting' };
    }

    board = seat(board, n.candidate, today);
    return { ...n, outcome: 'accepted' };
  });

  return { ...config, board, nominations };
}

/**
 * Declare (or clear, with an empty `until`) `login`'s own absence. Only an
 * *active* member can be marked away: an absence recorded against someone
 * who has left the board would read as "away, back on the 12th" for a seat
 * nobody holds, so the entry is left untouched instead.
 *
 * `until` is the inclusive last day away, the same reading `activeBoard`
 * applies. There is no proxy and no third-party declaration: the screen
 * passes the signed-in login, and the return is automatic when the date
 * passes -- nothing has to be written to come back.
 */
export function declareUnavailability(config: Config, login: string, until: string): Config {
  return {
    ...config,
    board: config.board.map(m =>
      m.login === login && m.status === 'active' ? { ...m, unavailable_until: until } : m,
    ),
  };
}
