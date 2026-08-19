const REPO = 'example-instance/example-cockpit';

export class GitHubError extends Error {
  status: number;
  constructor(status: number, msg: string) { super(msg); this.status = status; }
}

export async function gh(path: string, opts: RequestInit & { token: string }) {
  const { token, headers, ...rest } = opts;
  const r = await fetch(`https://api.github.com/repos/${REPO}${path}`, {
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
