import { instanceIdentity } from '../instance';
import { request } from '../net/request';
// The repository this cockpit reads and writes. `owner/name` is the
// instance's, declared once in `config/instance.json` and carried into
// this bundle by `vite.config.ts`'s own define -- a duplicate that left
// the literal here would have every Board member's ballot written into
// somebody else's repository, or refused by it.
const repo = () => instanceIdentity().repository;

export class GitHubError extends Error {
  status: number;
  constructor(status: number, msg: string) { super(msg); this.status = status; }
}

export async function gh(path: string, opts: RequestInit & { token: string }) {
  const { token, headers, ...rest } = opts;
  const r = await request(`https://api.github.com/repos/${repo()}${path}`, {
    ...rest,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      ...headers,
    },
  });
  if (!r.ok) {
    const body = await r.text();
    throw new GitHubError(r.status, `GitHub ${r.status}: ${body.slice(0, 200)}`);
  }
  return r.json();
}
