import type { Config } from '../data/types';

const ORG = 'The Example Collective';
const TEAM = 'editorial-board';

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
      if (j.state === 'active') return 'board';
      return 'organizer';
    }
  } catch {
    /* network or CORS — fall through to config fallback */
  }
  if (config?.board_members?.includes(login)) return 'board';
  return 'organizer';
}
