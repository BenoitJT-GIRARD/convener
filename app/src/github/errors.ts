import { GitHubError } from './client';

export type ErrorContext = 'load' | 'save';

/** Map a thrown error into a plain-language sentence a non-technical
 *  volunteer can act on. The raw detail (status, response body) is logged
 *  for diagnosis and never reaches the screen. */
export function friendlyError(e: unknown, context: ErrorContext): string {
  console.error(e);

  if (e instanceof GitHubError) {
    if (e.status === 401) return 'Your sign-in has expired. Sign in again.';
    // Not "your access token": on the device-flow sign-in there is no token
    // the volunteer ever saw, and the thing without the right is the account.
    // The recovery names the one person who can grant it, because a volunteer
    // told only that they may not write has nowhere to go next.
    if (e.status === 403) {
      return context === 'save'
        ? 'Your GitHub account does not have permission to save to this repository. ' +
            'Ask whoever set this instance up for write access.'
        : 'Your GitHub account does not have permission to read this. ' +
            'Ask whoever set this instance up for access.';
    }
    // "That" named nothing. Every 404 reaching here is a path this app asked
    // the Contents API for, so the sentence can say so and offer the one
    // person who can look.
    if (e.status === 404)
      return 'GitHub could not find that file. If this keeps happening, ask whoever set this instance up.';
    return 'GitHub is not responding. Try again in a moment.';
  }

  // ConflictError (github/mutate.ts) is already a plain-language sentence
  // naming the actual cause -- pass it through rather than flattening it.
  if (e instanceof Error && e.name === 'ConflictError') return e.message;

  // BallotRejected (state/ballots.ts) is likewise already a plain sentence
  // telling the volunteer what to add. The forms ask for the missing piece
  // before writing, so this is a backstop -- but a governance rule must never
  // surface as "GitHub is not responding".
  if (e instanceof Error && e.name === 'BallotRejected') return e.message;

  // NominationRejected (state/board.ts) is the same arrangement: the Board
  // screen keeps the control disabled and shows the reason before anyone
  // submits, so reaching here means a rule fired inside a `mutate`
  // transformation -- which must still read as the governance rule it is.
  if (e instanceof Error && e.name === 'NominationRejected') return e.message;

  // DateRejected (state/dates.ts) is the date negotiation refusing an offer,
  // a reply or a lock-in. The forms keep the control disabled and show the
  // same sentence beforehand, so reaching here means the rule fired inside a
  // `mutate` transformation replayed against freshly-read data -- exactly the
  // moment a volunteer needs to read that the speaker has not accepted that
  // evening, rather than that GitHub is unwell.
  if (e instanceof Error && e.name === 'DateRejected') return e.message;

  // AssignmentRejected (state/assignment.ts) is a name being put down against
  // a line the journey does not have. The checklist only ever offers the lines
  // it is rendering, so reaching here means the runbook changed underneath a
  // page somebody left open -- and the sentence says which line, not that
  // GitHub is unwell.
  if (e instanceof Error && e.name === 'AssignmentRejected') return e.message;

  // DataShapeError (data/validate.ts) is a data file that does not match the
  // model: the app cannot read it, and no amount of retrying will change
  // that. The sentence names the file and the field, and says who can fix
  // it -- a malformed repository is an operator problem, and the volunteer
  // who opened the app must not be left reading a parser error, nor told to
  // check their connection over a file that needs editing on GitHub.
  if (e instanceof Error && e.name === 'DataShapeError') return e.message;

  // PublicationBlocked (state/governance.ts) is the publication gate (G-10,
  // G-15) refusing to archive. `PublicationGate` keeps the button disabled
  // and shows the same sentence beforehand, so reaching here means the rule
  // fired inside a `mutate` transformation replayed against freshly-read
  // data -- which is precisely when the volunteer most needs to read "the
  // speaker has not given permission" rather than a network error.
  if (e instanceof Error && e.name === 'PublicationBlocked') return e.message;

  // Anything else (a rejected fetch: offline, DNS failure, captive portal)
  // reaches here as a bare TypeError. GitHub never answered at all, so it is
  // not known to be unwell -- and on the commonest cause of this branch, a
  // volunteer on a train, it is perfectly healthy. The sentence claims only
  // what is actually established, and offers the check that fixes it most
  // often. A status this app *did* receive keeps the older sentence above,
  // where "not responding" is what was observed.
  return 'Could not reach GitHub. Check your connection, then try again.';
}
