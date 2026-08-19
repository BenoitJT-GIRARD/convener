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

/** Anything with a scheme we are willing to send a volunteer to. */
const SAFE_SCHEME = /^(https?:|mailto:)/i;
const HAS_SCHEME = /^[a-z][a-z0-9+.-]*:/i;

/**
 * Where a link written inside a handbook file points once that file is
 * rendered by the app.
 *
 * Handbook files are written to be read in the repository, so their links are
 * relative to the file: `../assets/flyer-template.svg` from
 * `toolkit/visual-kit.md`. Rendered in the app the browser would resolve that
 * against the *route* — `/workshop-series/templates` — and hand the volunteer
 * a 404. Resolving it against the file's own directory instead, under the same
 * `handbook/` path the content was fetched from, makes the download link in
 * the handbook the download link in the app, with one file on disk behind
 * both. A link with an unknown scheme resolves to nothing rather than being
 * passed through: this replaces react-markdown's own sanitiser, so it keeps
 * the guarantee that sanitiser gave.
 */
export function handbookUrl(key: string, href: string | null | undefined): string {
  if (!href) return '';
  if (href.startsWith('#') || href.startsWith('/')) return href;
  if (HAS_SCHEME.test(href)) return SAFE_SCHEME.test(href) ? href : '';
  const entry = CONTENT_REGISTRY[key];
  if (!entry) return '';
  const hashAt = href.indexOf('#');
  const path = hashAt === -1 ? href : href.slice(0, hashAt);
  const hash = hashAt === -1 ? '' : href.slice(hashAt);
  const segments = entry.file.split('/').slice(0, -1);
  for (const part of path.split('/')) {
    if (part === '' || part === '.') continue;
    else if (part === '..') segments.pop();
    else segments.push(part);
  }
  return `${BASE}/handbook/${segments.map(encodeURIComponent).join('/')}${hash}`;
}

export async function fetchContent(key: string, _token: string | null): Promise<string> {
  if (cache.has(key)) return cache.get(key)!;
  const entry = CONTENT_REGISTRY[key];
  if (!entry) return `*Missing content for \`${key}\`*`;
  const url = `${BASE}/handbook/${entry.file}`;
  let r: Response;
  try {
    r = await fetch(url);
  } catch (e) {
    console.error(e);
    throw new Error('Could not load this content. Check your connection and try again.', {
      cause: e,
    });
  }
  if (!r.ok) {
    console.error(`Content fetch failed (${r.status}): handbook/${entry.file}`);
    throw new Error('This content could not be loaded right now.');
  }
  const text = await r.text();
  cache.set(key, text);
  return text;
}

export function invalidateContent(key?: string) {
  if (key) cache.delete(key);
  else cache.clear();
}
