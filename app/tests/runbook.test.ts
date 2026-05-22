import { describe, it, expect } from 'vitest';
import { RUNBOOK, computeProgress } from '../src/data/runbook';

describe('runbook', () => {
  it('has at least 10 steps across windows', () => {
    expect(RUNBOOK.length).toBeGreaterThanOrEqual(10);
  });
  it('every step has a unique key', () => {
    const keys = RUNBOOK.map(s => s.key);
    expect(new Set(keys).size).toBe(keys.length);
  });
  it('computes 0% with no progress', () => {
    expect(computeProgress({})).toEqual({ done: 0, total: RUNBOOK.length, pct: 0 });
  });
  it('computes 100% when all checked', () => {
    const all = Object.fromEntries(RUNBOOK.map(s => [s.key, true]));
    expect(computeProgress(all).pct).toBe(100);
  });
  it('ignores unknown keys in progress map', () => {
    const p = computeProgress({ unknown: true });
    expect(p.done).toBe(0);
  });
});
