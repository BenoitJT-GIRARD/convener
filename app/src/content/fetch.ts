import { CONTENT_REGISTRY } from './registry';
import { isDemoMode } from '../data/demo';

const cache = new Map<string, string>();
const REPO = 'example-instance/workshop-series';

export async function fetchContent(key: string, token: string | null): Promise<string> {
  if (cache.has(key)) return cache.get(key)!;
  const entry = CONTENT_REGISTRY[key];
  if (!entry) return `*Missing content for \`${key}\`*`;
  if (isDemoMode() || !token) {
    return `_(demo) content not loaded for **${key}** — file: \`docs/${entry.file}\`_`;
  }
  const url = `https://api.github.com/repos/${REPO}/contents/docs/${entry.file}`;
  const r = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github.raw',
    },
  });
  if (!r.ok) throw new Error(`Content fetch failed (${r.status}): docs/${entry.file}`);
  const text = await r.text();
  cache.set(key, text);
  return text;
}

export function invalidateContent(key?: string) {
  if (key) cache.delete(key);
  else cache.clear();
}
