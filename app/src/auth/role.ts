import type { Config } from '../data/types';
import { isBoardMember } from '../state/board';
import { parisToday } from '../state/derived';
import { organisationLogin } from '../instance';
import { request } from '../net/request';

/** The GitHub team whose membership this check reads. The *slug* is the
 *  product's -- every duplicate creates a team by this name, and
 *  `docs/reference/operations.md` says so -- while the organisation it
 *  belongs to is the instance's, taken from the one repository name
 *  `config/instance.json` declares. Two facts, each in the place that
 *  owns it. */
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
    const r = await request(
      `https://api.github.com/orgs/${organisationLogin()}/teams/${TEAM}/memberships/${login}`,
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
  if (config) {
    const today = parisToday();
    if (isBoardMember(config, login, today)) return 'board';
  }
  return 'organizer';
}
