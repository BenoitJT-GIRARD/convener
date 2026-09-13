/**
 * Writing `instance/data/config.yml` without deleting the reasoning in it.
 *
 * **What went wrong, measured.** A cockpit write of this file used to be a
 * parse-and-serialise: `js-yaml` drops every comment on the way in, and the
 * writer put a one-line constant back where the file's own header had been.
 * On a live instance, advancing an integer took the file from 31 comment
 * lines to 1 — thirty lines explaining why those logins are GitHub logins and
 * not names, how the team is resolved, and which thresholds are the product's
 * defaults kept rather than chosen — in a commit whose subject said it had
 * advanced a counter.
 *
 * `config.yml` is the one file this product asks an operator to *reason*
 * about rather than fill in, its comments are the only place those decisions
 * are written down, and `boundary.yml` gives the file to the instance — so
 * nothing upstream will ever put them back.
 *
 * **The rule here is the one `settings/edit.ts` already keeps for a single
 * number, generalised to a block:** re-emit the original bytes for every
 * top-level key whose value did not change, and the canonical dump's bytes
 * only for the ones that did. A comment sitting above a key travels with that
 * key. Measured against the shipped example: all 27 of its comment lines sit
 * outside the one block the Board screen ever rewrites, so a nomination now
 * leaves every one of them where it was.
 *
 * **The dump itself is untouched**, deliberately. `serializeConfig` and
 * `CONFIG_HEADER` are pinned byte for byte against `store.dump_config` on the
 * Python side (`tools/tests/cli/test_yaml_boundary.py`), and that agreement is
 * about what a *fresh* file looks like. This module changes what a writer does
 * with the dump, not what the dump is.
 *
 * **Key order is the original's**, for keys the file already had. The canonical
 * order is what a fresh dump produces and what the boundary pins; re-ordering a
 * file somebody arranged, on a write that moved one integer, is the other half
 * of the damage this fixes.
 */
import type { Config } from './types';
import { CONFIG_HEADER, parseConfig, serializeConfig, withConfigHeader } from './yaml';

/** A top-level key is unindented, a YAML name, and followed by a colon. Narrow
 *  on purpose: anything this does not recognise as a key line belongs to the
 *  block above it, which is the safe direction — an unrecognised line is
 *  carried through unchanged rather than dropped. */
const KEY_LINE = /^([A-Za-z_][A-Za-z0-9_]*):/;

interface Block {
  /** The comment and blank lines immediately above the key, which are about
   *  it and move with it. */
  comments: string[];
  /** The key line and everything indented under it. */
  lines: string[];
}

interface Parsed {
  /** Everything before the first key: the file's own header. */
  lead: string[];
  blocks: Map<string, Block>;
  order: string[];
}

/** Split a YAML document into its top-level blocks, keeping every byte.
 *
 *  Comment and blank lines are attached to the key *below* them rather than
 *  the one above: that is what a reader means by them, and it is what makes a
 *  removed key take its own explanation with it instead of orphaning it above
 *  the next one.
 */
function parseBlocks(text: string): Parsed {
  const lines = text.split('\n');
  const lead: string[] = [];
  const blocks = new Map<string, Block>();
  const order: string[] = [];
  let pending: string[] = [];
  let current: Block | null = null;

  for (const line of lines) {
    const match = KEY_LINE.exec(line);
    if (match) {
      const key = match[1];
      current = { comments: pending, lines: [line] };
      pending = [];
      blocks.set(key, current);
      order.push(key);
      continue;
    }
    const isNote = line.trim() === '' || line.trimStart().startsWith('#');
    if (current === null) {
      lead.push(line);
      continue;
    }
    if (isNote) {
      pending.push(line);
      continue;
    }
    // Not a note and not a key: an indented continuation, or a list item.
    // Whatever was pending was inside this block after all.
    current.lines.push(...pending, line);
    pending = [];
  }
  // Whatever is left is the tail of the file, under the last key it followed.
  if (current !== null) current.lines.push(...pending);
  else lead.push(...pending);
  return { lead, blocks, order };
}

function sameValue(before: Config, next: Config, key: string): boolean {
  const a = (before as unknown as Record<string, unknown>)[key];
  const b = (next as unknown as Record<string, unknown>)[key];
  return JSON.stringify(a) === JSON.stringify(b);
}

/**
 * The bytes to write for `next`, keeping everything about `original` that
 * `next` did not change.
 *
 * An empty or unreadable original falls back to the canonical dump: there is
 * nothing to preserve, and refusing to write would be worse than writing a
 * fresh file. Every other path re-emits original bytes wherever it can.
 */
export function configTextFor(original: string, next: Config): string {
  if (original.trim() === '') return withConfigHeader(serializeConfig(next));

  let before: Config;
  try {
    before = parseConfig(original);
  } catch {
    return withConfigHeader(serializeConfig(next));
  }

  const kept = parseBlocks(original);
  const fresh = parseBlocks(withConfigHeader(serializeConfig(next)));

  const out: string[] = [];
  out.push(...(kept.lead.length > 0 ? kept.lead : [CONFIG_HEADER.trimEnd()]));

  // The file's own order, so a write that changed one value leaves a
  // one-block diff rather than a reordered file.
  //
  // There is no second pass for keys the dump has and the file does not, and
  // there cannot be one: `readConfig` refuses a file missing a key outright
  // rather than defaulting it, so `parseConfig` above would have thrown and
  // this function would have fallen back to a fresh dump long before here. A
  // loop for that case would be a branch nothing can reach, which is a worse
  // thing to leave behind than the case it imagines.
  for (const key of kept.order) {
    const block = fresh.blocks.get(key);
    if (block === undefined) continue; // the key is gone; its comments go too
    const original_block = kept.blocks.get(key)!;
    out.push(...original_block.comments);
    out.push(...(sameValue(before, next, key) ? original_block.lines : block.lines));
  }

  const text = out.join('\n');
  return text.endsWith('\n') ? text : `${text}\n`;
}
