/** Validate a token against GitHub's API.
 *
 * Returns `null` both when the token is rejected (a normal, expected
 * outcome) and when the network request itself fails — offline, DNS
 * failure, captive portal. Callers must not assume this resolves; treat
 * `null` as "could not sign in right now" in both cases, and never let it
 * reject uncaught. */
export async function validateToken(token: string): Promise<{ login: string } | null> {
  let r: Response;
  try {
    r = await fetch('https://api.github.com/user', {
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json' },
    });
  } catch {
    return null;
  }
  if (!r.ok) return null;
  const data = await r.json();
  return { login: data.login };
}
