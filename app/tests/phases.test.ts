import { describe, it, expect } from 'vitest';
import { phaseOf, gatesComplete, PHASES } from '../src/state/phases';

describe('phases', () => {
  it('returns phase by status', () => {
    expect(phaseOf('lead')?.label).toMatch(/Lead/);
    expect(phaseOf('archived')).toBeUndefined();
  });

  it('every runbook key is unique across all phases', () => {
    const keys: string[] = [];
    for (const p of PHASES) for (const i of p.items) keys.push(i.key);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it('every gate item is namespaced under its phase status', () => {
    for (const p of PHASES) {
      for (const i of p.items) {
        expect(i.key.startsWith(`${p.status}/`)).toBe(true);
      }
    }
  });

  it('gatesComplete only true when all gates checked', () => {
    const phase = phaseOf('approved')!;
    expect(gatesComplete(phase, {})).toBe(false);
    expect(gatesComplete(phase, { 'approved/hosts-decided': true })).toBe(false);
    expect(
      gatesComplete(phase, {
        'approved/hosts-decided': true,
        'approved/invitation-sent': true,
      }),
    ).toBe(true);
  });

  it('lead phase has no gates so gatesComplete is false', () => {
    expect(gatesComplete(phaseOf('lead')!, { 'lead/research-speaker': true })).toBe(false);
  });
});
