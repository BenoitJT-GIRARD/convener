import type { Speaker } from '../data/types';

export interface SubstitutionContext {
  speaker?: Speaker;
  host?: string;
  today?: string;
}

const MISSING = (path: string) => `«missing: ${path}»`;

export function substitute(text: string, ctx: SubstitutionContext): string {
  return text.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (_, path) => {
    const parts = path.split('.');
    let cur: any = ctx;
    for (const p of parts) {
      if (cur && typeof cur === 'object' && p in cur) cur = cur[p];
      else return MISSING(path);
    }
    if (cur === null || cur === undefined || cur === '') return MISSING(path);
    return String(cur);
  });
}
