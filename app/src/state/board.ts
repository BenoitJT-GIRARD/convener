/**
 * Who is on the board, who is available, and who a new lead falls to.
 *
 * `governance.ts` computes the vote threshold from the *eligible* board --
 * active members, minus those who declared an absence, minus those recused
 * on a lead. This module supplies the first two of those: `activeBoard`
 * produces the active-member logins and the subset of them unavailable on a
 * given date; `governance.eligibleVoters` does the subtracting.
 *
 * `assignLead` (G-17) crosses the language boundary: `tools/convener_ops/proposal.py`
 * implements the same rule for the public-form intake path, and both are
 * pinned by `tools/tests/fixtures/governance-cases.json`'s `assign_lead_cases`.
 */
import type { BoardMember, Config, Speaker } from '../data/types';

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
 * The active, available board member to whom a new lead with no member
 * proposer falls (G-17): whoever carries the fewest open leads (status
 * `lead`, `proposed_by` that member). A tie goes to whoever's most recent
 * open lead is the oldest -- i.e. whoever has gone longest without a new
 * one -- using the id's numeric suffix as a stand-in for creation order,
 * since ids are assigned in strictly increasing order (see
 * `tools/convener_ops/proposal.py::to_lead`). Any further tie (including "never
 * assigned") falls back to alphabetical login order, so the result never
 * depends on `config.board`'s incidental ordering and repeated calls with
 * the same input always agree.
 *
 * Returns `''` -- never throws -- when no member is both active and
 * available: the caller displays that the assignment is pending rather than
 * surfacing a raw error to a volunteer.
 */
export function assignLead(speakers: Speaker[], config: Config, on: string): string {
  const { logins, unavailable } = activeBoard(config, on);
  const away = new Set(unavailable);
  const eligible = logins.filter(login => !away.has(login)).sort();
  if (eligible.length === 0) return '';

  const openLeadIds = new Map<string, number[]>(eligible.map(login => [login, []]));
  for (const s of speakers) {
    if (s.status !== 'lead') continue;
    const ids = openLeadIds.get(s.proposed_by);
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
