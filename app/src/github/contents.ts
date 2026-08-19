import { gh } from './client';
import type { FileStore } from './mutate';
import type { Subject } from '../state/decisions';

export interface PutFileResponse {
  content: { sha: string };
}

export async function getFile(path: string, token: string): Promise<{ text: string; sha: string }> {
  const data = await gh(`/contents/${path}`, { token, method: 'GET' });
  // base64 -> utf-8 (handle non-ASCII like accents in YAML notes)
  const bin = atob((data.content as string).replace(/\n/g, ''));
  const bytes = Uint8Array.from(bin, c => c.charCodeAt(0));
  const text = new TextDecoder('utf-8').decode(bytes);
  return { text, sha: data.sha };
}

/** The `message` is the commit subject and is a `Subject` for the reason
 *  `state/decisions.ts` gives: it is permanent, and this is the call that
 *  makes it so. `mutate` asks the grammar of the string as well, at the one
 *  point every write of this app goes through. */
export async function putFile(
  path: string, text: string, sha: string, message: Subject, token: string
): Promise<PutFileResponse> {
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

/** The real store, backed by the GitHub Contents API. */
export function githubStore(token: string): FileStore {
  return {
    read: (path) => getFile(path, token),
    write: async (path, text, sha, message) => {
      const res = await putFile(path, text, sha, message, token);
      return { sha: res.content.sha };
    },
  };
}
