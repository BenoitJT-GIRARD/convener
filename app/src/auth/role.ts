import type { Config } from '../data/types';

const ORG = 'The Example Collective';
const TEAM = 'editorial-board';

/**
 * Resolve a user's role.
 *
 * A 404 (or 403) from the memberships endpoint is an *answer*: the user is
 * not on the team. Only an unreachable or failing API justifies the config
 * fallback -- conflating the two would silently promote people the API had
 * already refused.
 */
export async function detectRole(
  login: string,
  token: string,
  config: Config | null,
): Promise<'board' | 'organizer'> {
  try {
    const r = await fetch(
      `https://api.github.com/orgs/${ORG}/teams/${TEAM}/memberships/${login}`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: 'application/vnd.github+json',
        },
      },
    );

    if (r.ok) {
      const j = await r.json();
      return j.state === 'active' ? 'board' : 'organizer';
    }

    // Authoritative negative answers -- the API said no, so it wins over
    // the config fallback below.
    if (r.status === 404 || r.status === 403) return 'organizer';

    // Anything else (5xx, rate limiting) is a failure, not an answer: fall
    // through to the config-based fallback.
  } catch {
    /* network or CORS -- fall through to config fallback */
  }
  if (config?.board_members?.includes(login)) return 'board';
  return 'organizer';
}
