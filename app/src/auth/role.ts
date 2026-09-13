import type { Config } from '../data/types';
import { isBoardMember } from '../state/board';
import { parisToday } from '../state/derived';
import { organisationLogin } from '../instance';
import { request } from '../net/request';

/** The GitHub team whose membership this check reads. The *slug* is the
 *  product's -- every duplicate creates a team by this name, and
 *  `docs/operating/operations.md` says so -- while the organisation it
 *  belongs to is the instance's, taken from the one repository name
 *  `instance/config.json` declares. Two facts, each in the place that
 *  owns it. */
const TEAM = 'editorial-board';

/**
 * Resolve a user's role.
 *
 * A 404 from the memberships endpoint is an *answer*: GitHub returns it for
 * a login that is not on the team, so it wins over the config fallback --
 * conflating the two would silently promote people the API had already
 * refused.
 *
 * A 403 is not that. It says the caller may not ask, and it is what this
 * application's own sign-in produces by design: `declarations/standing-up.yml`
 * registers the App with one repository permission and says to leave every
 * other permission alone, so its user token cannot reach an *organisation*
 * endpoint and GitHub answers "Resource not accessible by integration". The
 * same 403 arrives from a fine-grained personal access token scoped to the
 * repository, which `docs/engineering/architecture.md` offers as the way in
 * when the App is not set up.
 *
 * Read as an answer, that refusal demoted every Board member the standing-up
 * sequence had just installed: the ballot section is drawn for `board`, so a
 * Board that followed the procedure exactly could not vote. It falls through
 * to the config below instead, which is where the Board is declared anyway.
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

    // The one authoritative negative -- the API said no, so it wins over
    // the config fallback below.
    if (r.status === 404) return 'organizer';

    // Anything else (403, 5xx, rate limiting) is a failure to obtain an
    // answer, not an answer: fall through to the config-based fallback.
  } catch {
    /* network or CORS -- fall through to config fallback */
  }
  if (config) {
    const today = parisToday();
    if (isBoardMember(config, login, today)) return 'board';
  }
  return 'organizer';
}
