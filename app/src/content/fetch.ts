import { CONTENT_REGISTRY } from './registry';

const cache = new Map<string, string>();
const BASE = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');

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
