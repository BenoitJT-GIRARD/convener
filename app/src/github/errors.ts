import { GitHubError } from './client';

export type ErrorContext = 'load' | 'save';

/** Map a thrown error into a plain-language sentence a non-technical
 *  volunteer can act on. The raw detail (status, response body) is logged
 *  for diagnosis and never reaches the screen. */
export function friendlyError(e: unknown, context: ErrorContext): string {
  console.error(e);

  if (e instanceof GitHubError) {
    if (e.status === 401) return 'Your sign-in has expired. Sign in again.';
    if (e.status === 403) {
      return context === 'save'
        ? 'Your access token does not have permission to save.'
        : 'Your access token does not have permission to load this.';
    }
    if (e.status === 404) return 'That could not be found on GitHub.';
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
  // reaches here as a bare TypeError with no useful message to show.
  return 'GitHub is not responding. Try again in a moment.';
}
