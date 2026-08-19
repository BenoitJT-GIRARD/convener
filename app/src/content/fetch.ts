import { CONTENT_REGISTRY, REPO_URL } from './registry';
import { expandIncludes, sectionOf } from './transclude';

/** Rendered text, by content key: what a screen asks for. */
const cache = new Map<string, string>();
/** Raw file text, by path under `docs/`: what the network was asked for.
 *  A page and the fragments included in it are usually different keys over
 *  the same few files, and a fragment is by definition a second read of a
 *  file the reader may already have. Caching the file rather than only the
 *  key is what keeps transclusion from turning one page into six requests. */
const rawCache = new Map<string, string>();
const BASE = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');
const REPO_EDIT_URL = `${REPO_URL}/edit/main/docs`;

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

/** One file under `docs/`, fetched once. */
async function loadFile(file: string): Promise<string> {
  const known = rawCache.get(file);
  if (known !== undefined) return known;
  const url = `${BASE}/handbook/${file}`;
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
    console.error(`Content fetch failed (${r.status}): handbook/${file}`);
    throw new Error('This content could not be loaded right now.');
  }
  const text = await r.text();
  rawCache.set(file, text);
  return text;
}

/**
 * The markdown a screen renders for a content key.
 *
 * Three steps, and the last two are why `anchor` exists. The file is read;
 * an entry carrying an anchor is narrowed to that one section, so a fragment
 * key renders a passage rather than a page; and every `{{> key }}` line in
 * what is left is replaced by the passage it names, under a line saying where
 * that passage is kept. Substitution of `{{ speaker.… }}` happens after this,
 * in `InlineContent`, so an included passage is filled in exactly as the page
 * around it is.
 */
export async function fetchContent(key: string, _token: string | null): Promise<string> {
  if (cache.has(key)) return cache.get(key)!;
  const entry = CONTENT_REGISTRY[key];
  if (!entry) return `*Missing content for \`${key}\`*`;
  const raw = await loadFile(entry.file);
  let text = raw;
  if (entry.anchor) {
    const section = sectionOf(raw, entry.anchor);
    text = section ? section.body : `«missing section: ${entry.anchor} in ${key}»`;
  }
  text = await expandIncludes(text, loadFile, [key]);
  cache.set(key, text);
  return text;
}

export function invalidateContent(key?: string) {
  if (key) cache.delete(key);
  else {
    cache.clear();
    rawCache.clear();
  }
}
