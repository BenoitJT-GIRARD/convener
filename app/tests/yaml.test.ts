import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect } from 'vitest';
import { parseSpeakers, serializeSpeakers, parseConfig, serializeConfig } from '../src/data/yaml';
import { SPEAKERS_HEADER, withSpeakersHeader, withConfigHeader, stripHeader } from '../src/data/yaml';
import { SPEAKERS, CONFIG } from './boundary-samples';
import { speaker as blank } from './data-doubles';
import type { Speaker } from '../src/data/types';

/** A blank record, written in the model's own field order: the reader in
 *  `data/validate.ts` rebuilds every record in that order, so serialising
 *  what it returns is stable no matter what order the file used. */
function speaker(id: string, status: Speaker['status'] = 'lead'): Speaker {
  return {
    ...blank(),
    id,
    name: `Speaker ${id}`,
    status,
  };
}

/** The full record from the shared boundary samples: everything populated,
 *  accents included. The fixture below is what serialising it produces. */
const sample = SPEAKERS[0];
const sampleCfg = CONFIG;

describe('yaml v2 schema', () => {
  it('round-trips a unified speaker', () => {
    const text = serializeSpeakers([sample]);
    const [back] = parseSpeakers(text);
    expect(back).toEqual(sample);
  });
  it('parses an empty list', () => {
    expect(parseSpeakers('')).toEqual([]);
  });
  it('round-trips config with seminar_duration_minutes', () => {
    const text = serializeConfig(sampleCfg);
    const back = parseConfig(text);
    expect(back).toEqual(sampleCfg);
  });
});

describe('speakers serialisation round-trip', () => {
  it('keeps the header exactly once', () => {
    const text = withSpeakersHeader(serializeSpeakers([speaker('spk-001')]));
    expect(text.startsWith(SPEAKERS_HEADER)).toBe(true);
    expect(text.split(SPEAKERS_HEADER).length - 1).toBe(1);
  });

  it('parses back what it serialised', () => {
    const original = [speaker('spk-001'), speaker('spk-002', 'approved')];
    const text = withSpeakersHeader(serializeSpeakers(original));
    expect(parseSpeakers(stripHeader(text))).toEqual(original);
  });

  it('is stable: serialising twice gives the identical text', () => {
    const once = withSpeakersHeader(serializeSpeakers([speaker('spk-001')]));
    const twice = withSpeakersHeader(
      serializeSpeakers(parseSpeakers(stripHeader(once))),
    );
    expect(twice).toBe(once);
  });
});

/** Read a checked-in boundary fixture as the bytes it is on disk. */
function fixture(name: string): string {
  return readFileSync(resolve(__dirname, `../../tools/tests/fixtures/${name}`), 'utf-8');
}

describe('the JS/Python YAML boundary (D-14)', () => {
  // `tools/tests/test_yaml_boundary.py` loads these same two files, writes
  // them back out through the Python writer, and asserts the bytes are
  // unchanged. Here is the other end of that round-trip: the fixtures are
  // what this app emits, byte for byte, and parsing them gives back the
  // very objects they were written from. A field either side serialises
  // differently therefore fails here or there -- it cannot reach `data/`.
  //
  // To regenerate after a deliberate schema change: run the suite, read the
  // diff the assertion prints, and update the fixture to match. Never the
  // other way round -- the fixture is not hand-typed, and a hand-typed
  // approximation is what let `time: 12:30` through in phase 1.
  it('writes speakers.yml exactly as the checked-in fixture', () => {
    expect(withSpeakersHeader(serializeSpeakers(SPEAKERS))).toBe(
      fixture('speakers-from-app.yml'),
    );
  });

  it('writes config.yml exactly as the checked-in fixture', () => {
    expect(withConfigHeader(serializeConfig(CONFIG))).toBe(
      fixture('config-from-app.yml'),
    );
  });

  it('reads its own speakers fixture back into the very records it wrote', () => {
    expect(parseSpeakers(stripHeader(fixture('speakers-from-app.yml')))).toEqual(SPEAKERS);
  });

  it('reads its own config fixture back into the very config it wrote', () => {
    expect(parseConfig(stripHeader(fixture('config-from-app.yml')))).toEqual(CONFIG);
  });

  it('keeps a bare time out of YAML 1.1 arithmetic: 12:30 is text, never 750', () => {
    const [back] = parseSpeakers(stripHeader(fixture('speakers-from-app.yml')));
    expect(back.time).toBe('12:30');
    expect(fixture('speakers-from-app.yml')).toContain("time: '12:30'");
    // Quoted too, though PyYAML's int resolver would not have misread this
    // one: what the two writers agree on is the bytes, not a rule of thumb
    // about which times are dangerous.
    expect(fixture('speakers-from-app.yml')).toContain("time: '09:05'");
  });

  it('keeps text that looks like a boolean or a number as text', () => {
    const [, , odd] = parseSpeakers(stripHeader(fixture('speakers-from-app.yml')));
    expect(odd.title).toBe('yes');
    expect(odd.country).toBe('NO');
    expect(odd.proposed_by).toBe('on');
    expect(odd.affiliation).toBe('0123');
    expect(odd.notes).toBe('3.14');
    expect(odd.name).toBe('True');
  });

  it('keeps proposed_by and assigned_to apart, and an empty login empty', () => {
    const [full, blank] = parseSpeakers(stripHeader(fixture('speakers-from-app.yml')));
    expect(full.proposed_by).toBe('Émilie Dupré');
    expect(full.assigned_to).toBe('alice');
    expect(blank.assigned_to).toBe('');
    expect(blank.proposed_by).toBe('');
  });

  it('tells a recorded zero from a metric nobody filled in', () => {
    const [full, blank] = parseSpeakers(stripHeader(fixture('speakers-from-app.yml')));
    expect(full.metrics.registrations).toBe(0);
    expect(blank.metrics.registrations).toBeNull();
  });

  it('carries every governance shape the two languages share', () => {
    const [full] = parseSpeakers(stripHeader(fixture('speakers-from-app.yml')));
    expect(full.selection.ballots.map(b => b.value)).toEqual([
      'yes', 'abstain', 'recused', 'yes',
    ]);
    expect(full.selection.opened_on).toBe('2025-12-20');
    expect(full.selection.decided_on).toBe('2026-01-07');
    expect(full.career_stage).toBe('group-leader');
    expect(full.publication.objections).toHaveLength(2);
    expect(full.publication.objections[1].resolved_on).toBe('');

    const cfg = parseConfig(stripHeader(fixture('config-from-app.yml')));
    expect(cfg?.board.map(m => m.status)).toEqual([
      'active', 'active', 'active', 'active', 'inactive',
    ]);
    expect(cfg?.board[1].unavailable_until).toBe('2026-09-01');
    expect(cfg?.nominations.map(n => n.outcome)).toEqual([
      'deferred', 'waiting', 'accepted',
    ]);
    expect(cfg?.nominations[0].objections[0].member).toBe('bob');
  });
});
