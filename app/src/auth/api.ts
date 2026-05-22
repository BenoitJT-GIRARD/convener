export async function validateToken(token: string): Promise<{ login: string } | null> {
  const r = await fetch('https://api.github.com/user', {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json' },
  });
  if (!r.ok) return null;
  const data = await r.json();
  return { login: data.login };
}
