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

  // Anything else (a rejected fetch: offline, DNS failure, captive portal)
  // reaches here as a bare TypeError with no useful message to show.
  return 'GitHub is not responding. Try again in a moment.';
}
