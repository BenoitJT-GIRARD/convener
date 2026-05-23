import { CONTENT_REGISTRY } from './registry';

const cache = new Map<string, string>();
const BASE = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');
const REPO_EDIT_URL = 'https://github.com/example-instance/workshop-series/edit/main/docs';

/** GitHub web-editor URL for the markdown file behind a content key, or null. */
export function editUrlFor(key: string): string | null {
  const entry = CONTENT_REGISTRY[key];
  if (!entry) return null;
  return `${REPO_EDIT_URL}/${entry.file}`;
}

export async function fetchContent(key: string, _token: string | null): Promise<string> {
  if (cache.has(key)) return cache.get(key)!;
  const entry = CONTENT_REGISTRY[key];
  if (!entry) return `*Missing content for \`${key}\`*`;
  const url = `${BASE}/handbook/${entry.file}`;
  const r = await fetch(url);
  if (!r.ok) {
    throw new Error(`Content fetch failed (${r.status}): handbook/${entry.file}`);
  }
  const text = await r.text();
  cache.set(key, text);
  return text;
}

export function invalidateContent(key?: string) {
  if (key) cache.delete(key);
  else cache.clear();
}
