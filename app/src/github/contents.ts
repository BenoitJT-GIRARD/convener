import { gh } from './client';

export async function getFile(path: string, token: string): Promise<{ text: string; sha: string }> {
  const data = await gh(`/contents/${path}`, { token, method: 'GET' });
  // base64 -> utf-8 (handle non-ASCII like accents in YAML notes)
  const bin = atob((data.content as string).replace(/\n/g, ''));
  const bytes = Uint8Array.from(bin, c => c.charCodeAt(0));
  const text = new TextDecoder('utf-8').decode(bytes);
  return { text, sha: data.sha };
}

export async function putFile(
  path: string, text: string, sha: string, message: string, token: string
) {
  // utf-8 -> base64
  const bytes = new TextEncoder().encode(text);
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  const content = btoa(bin);
  return gh(`/contents/${path}`, {
    token,
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, content, sha }),
  });
}
