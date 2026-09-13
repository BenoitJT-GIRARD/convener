import { request } from '../net/request';

/** What asking GitHub about a token can establish.
 *
 *  `refused` and `unreachable` were one value for a long time, and for most
 *  callers they still are (see `validateToken`). They are separated here for
 *  the one caller they are not the same to: a session held across a reload.
 *  Discarding it on `refused` is right — the token is no good and keeping it
 *  means a spinner and a sign-out message on every reload. Discarding it
 *  because GitHub answered 502, or because the request never left a train,
 *  charges a volunteer a full device flow for something that fixed itself,
 *  which is the cost D-03 exists to keep low. */
export type TokenCheck =
  | { outcome: 'valid'; login: string }
  | { outcome: 'refused' }
  | { outcome: 'unreachable' };

/** Ask GitHub about a token, and say which of the three happened.
 *
 *  A 5xx is `unreachable` rather than `refused` for the same reason
 *  `github/mutate.ts` replays one: the service said it could not answer, and
 *  that is not an answer about the token. Only a refusal GitHub actually
 *  made — 401, 403, and anything else in the 4xx range — is one. */
export async function checkToken(token: string): Promise<TokenCheck> {
  let r: Response;
  try {
    r = await request('https://api.github.com/user', {
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json' },
    });
  } catch {
    return { outcome: 'unreachable' };
  }
  if (!r.ok) {
    return r.status >= 500 ? { outcome: 'unreachable' } : { outcome: 'refused' };
  }
  const data = await r.json();
  return { outcome: 'valid', login: data.login };
}

/** Validate a token against GitHub's API.
 *
 * Returns `null` both when the token is rejected (a normal, expected
 * outcome) and when the network request itself fails — offline, DNS
 * failure, captive portal. Callers must not assume this resolves; treat
 * `null` as "could not sign in right now" in both cases, and never let it
 * reject uncaught. Where the difference matters, use `checkToken`. */
export async function validateToken(token: string): Promise<{ login: string } | null> {
  const checked = await checkToken(token);
  return checked.outcome === 'valid' ? { login: checked.login } : null;
}
