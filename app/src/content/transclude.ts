/**
 * A passage that belongs on two pages is written once and included twice.
 *
 * The information architecture asks for one home per notion; the review of the
 * handbook asked for the opposite, and was right: a volunteer who opens
 * "After the webinar" on the day needs the publication gate in front of them,
 * not a link to it. Both are satisfied by including the passage from the page
 * that owns it instead of copying it there.
 *
 * Copying would be cheaper and is what the handbook had been doing. It is also
 * how the two most dangerous passages in this repository drift: what the hosts
 * say before the recording starts, and what may be published afterwards. Two
 * copies of an irreversible procedure do not merely disagree — the one somebody
 * reads on the day is whichever was updated second, and nothing says which that
 * is.
 *
 * The mechanism is `ContentEntry.anchor`, declared with the registry since the
 * first version of it and never read until now. An entry with an anchor is a
 * *fragment*: the same file as the page it comes from, scoped to one of its
 * headings. Rendering a fragment key renders that section and nothing else, so
 * a fragment is not a second file that could hold a second version — it is a
 * window onto the first.
 *
 * A page includes one by putting the fragment's key on a line of its own:
 *
 *     {{> fragments/board-rules-publication-gate }}
 *
 * Unexpanded — read on GitHub, say — that line tells an editor the truth: this
 * passage is not maintained here. Expanded by the app, it becomes the passage
 * itself, under a line naming the page and section it came from and linking to
 * the file on GitHub. A reader who is about to act on a procedure can see in
 * one line where it is kept, which is the whole point: the attribution is not
 * decoration, it is the difference between reading a copy and reading the
 * source.
 */
import { CONTENT_REGISTRY, REPO_URL } from './registry';

/** A whole line that is nothing but an include: `{{> some/key }}`. */
export const INCLUDE_RE = /^[ \t]*\{\{>\s*([A-Za-z0-9/_-]+)\s*\}\}[ \t]*$/gm;

/** How deep an include may nest before we stop following it. */
const MAX_DEPTH = 4;

/** Visible markers, in the same shape as the renderer's `«missing: …»`: a
 *  handbook page that points at nothing must look broken, not merely read
 *  oddly. Every one of these is asserted absent across the served tree. */
const MISSING_KEY = (key: string) => `«missing include: ${key}»`;
const MISSING_SECTION = (key: string, anchor: string) =>
  `«missing section: ${anchor} in ${key}»`;
const CIRCULAR = (key: string) => `«circular include: ${key}»`;
const TOO_DEEP = (key: string) => `«include too deep: ${key}»`;

/**
 * The anchor a heading answers to, by GitHub's rule.
 *
 * Lower-cased, punctuation dropped rather than replaced, spaces to hyphens.
 * It matters that this is GitHub's rule and not one of our own: the anchors
 * declared in the registry are the same anchors the handbook already links to
 * in prose (`operations.md#inactivity-g-09`), and a second slug algorithm
 * would mean a heading could be reachable from a link and unreachable from an
 * include, or the reverse.
 */
export function slugify(heading: string): string {
  return heading
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N} -]/gu, '')
    .trim()
    // One hyphen per space, and spaces are not collapsed first: dropping the
    // em dash out of "The speaker's -- which must be present" leaves two
    // spaces and GitHub makes two hyphens of them. Collapsing here would give
    // an anchor that an include could reach and a link in the prose could not.
    .replace(/ /g, '-');
}

interface Heading {
  level: number;
  title: string;
  line: number;
}

function headings(text: string): Heading[] {
  const out: Heading[] = [];
  let fenced = false;
  text.split('\n').forEach((line, i) => {
    if (/^\s*```/.test(line)) fenced = !fenced;
    if (fenced) return;
    const m = /^(#{1,6})\s+(.*)$/.exec(line);
    if (m) out.push({ level: m[1].length, title: m[2].trim(), line: i });
  });
  return out;
}

/** The page's own title — the first `# ` heading, or the file name. */
export function pageTitle(text: string, file: string): string {
  const first = headings(text).find(h => h.level === 1);
  return first ? first.title : file;
}

export interface Section {
  /** The heading's text, as written. */
  title: string;
  /** Everything under it, up to the next heading of the same level or higher,
   *  with the heading line itself removed: the including page supplies its own
   *  heading, and two would be one too many. */
  body: string;
}

/** The section a slug names, or null when no heading answers to it. */
export function sectionOf(text: string, anchor: string): Section | null {
  const all = headings(text);
  const at = all.findIndex(h => slugify(h.title) === anchor);
  if (at === -1) return null;
  const start = all[at];
  const next = all.slice(at + 1).find(h => h.level <= start.level);
  const lines = text.split('\n');
  const body = lines.slice(start.line + 1, next ? next.line : lines.length);
  return { title: start.title, body: body.join('\n').trim() };
}

/** Where the passage is maintained, as a URL a reader can open. */
export function sourceUrl(key: string): string {
  const entry = CONTENT_REGISTRY[key];
  if (!entry) return '';
  return `${REPO_URL}/blob/main/docs/${entry.file}${entry.anchor ? `#${entry.anchor}` : ''}`;
}

/** The one line that turns a copy into a quotation. */
export function attribution(key: string, page: string, section: string): string {
  return `> **Included from [${page} — ${section}](${sourceUrl(key)}).** This passage is maintained there; changing it there changes it here.`;
}

/** Reads a file under `docs/`, by its path relative to `docs/`. */
export type LoadFile = (file: string) => Promise<string>;

/**
 * Replace every include line in `text` with the passage it names.
 *
 * `chain` is the keys already being expanded, innermost last. A fragment that
 * reaches itself renders a marker instead of hanging: a handbook that quotes
 * itself in a circle is a mistake somebody has to see, and a spinner is not
 * how they would see it.
 */
export async function expandIncludes(
  text: string,
  load: LoadFile,
  chain: readonly string[] = [],
): Promise<string> {
  // A fresh matcher each time: a shared global regexp carries `lastIndex`
  // between calls, and an expansion that skipped every other include would be
  // a bug nobody could reproduce twice.
  const wanted = [...text.matchAll(new RegExp(INCLUDE_RE.source, 'gm'))].map(m => m[1]);
  if (wanted.length === 0) return text;
  const resolved = new Map<string, string>();
  for (const key of new Set(wanted)) {
    resolved.set(key, await resolveOne(key, load, chain));
  }
  return text.replace(new RegExp(INCLUDE_RE.source, 'gm'), (_, key: string) =>
    resolved.get(key)!,
  );
}

async function resolveOne(
  key: string,
  load: LoadFile,
  chain: readonly string[],
): Promise<string> {
  if (chain.includes(key)) return CIRCULAR(key);
  if (chain.length >= MAX_DEPTH) return TOO_DEEP(key);
  const entry = CONTENT_REGISTRY[key];
  if (!entry) return MISSING_KEY(key);
  const raw = await load(entry.file);
  if (!entry.anchor) return await expandIncludes(raw, load, [...chain, key]);
  const section = sectionOf(raw, entry.anchor);
  if (!section) return MISSING_SECTION(key, entry.anchor);
  const body = await expandIncludes(section.body, load, [...chain, key]);
  return `${attribution(key, pageTitle(raw, entry.file), section.title)}\n\n${body}`;
}
