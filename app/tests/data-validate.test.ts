import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { parseConfig, parseSpeakers, serializeConfig, serializeSpeakers } from '../src/data/yaml';
import { DataShapeError } from '../src/data/validate';
import { friendlyError } from '../src/github/errors';
import { CONFIG, SPEAKERS } from './boundary-samples';
import { config, configYaml, speaker, speakersYaml } from './data-doubles';

/** The message a volunteer would actually be shown for `text`. */
function refusal(read: () => unknown): string {
  try {
    read();
  } catch (e) {
    expect(e).toBeInstanceOf(DataShapeError);
    return friendlyError(e, 'load');
  }
  throw new Error('the read was accepted, so there is no message to inspect');
}

function fixture(name: string): string {
  return readFileSync(resolve(__dirname, `../../tools/tests/fixtures/${name}`), 'utf-8');
}

describe('reading a file the app itself wrote', () => {
  it('accepts every record in the boundary fixture', () => {
    expect(parseSpeakers(serializeSpeakers(SPEAKERS))).toEqual(SPEAKERS);
    expect(parseConfig(serializeConfig(CONFIG))).toEqual(CONFIG);
  });

  it('reads an empty speakers file as no speakers, which is where the repo starts', () => {
    expect(parseSpeakers('')).toEqual([]);
    expect(parseSpeakers('# nothing but a comment\n')).toEqual([]);
  });

  it('rebuilds each record in the field order the model declares, so a rewrite settles at once', () => {
    // The reader returns records built field by field, in the order
    // `data/types.ts` declares. A file whose keys were typed in another
    // order is therefore normalised by the first save and stable after it,
    // instead of shuffling on every write.
    const once = serializeSpeakers(parseSpeakers(speakersYaml([{ id: 'spk-9' }])));
    const twice = serializeSpeakers(parseSpeakers(once));
    expect(twice).toBe(once);
    expect(once.indexOf('metrics:')).toBeLessThan(once.indexOf('notes:'));
  });
});

describe('what a volunteer is told when instance/data/config.yml is malformed', () => {
  it('names the file, the setting, and who can fix it -- and blames nobody', () => {
    const message = refusal(() => parseConfig(configYaml() + 'vote_threshold: 3\n'));
    expect(message).toContain('instance/data/config.yml');
    expect(message).toContain('vote_threshold');
    expect(message).toContain('does not use');
    expect(message).toContain('repository');
    // Not a network error, not a stack trace, not the reader's fault.
    expect(message).not.toMatch(/GitHub is not responding/);
    expect(message).not.toMatch(/undefined|TypeError|yaml/i);
    expect(message).not.toMatch(/\byou\b/i);
  });

  it('says which setting is missing rather than carrying on without it', () => {
    const partial = configYaml().replace(/^board_max: .*\n/m, '');
    // "Missing", in those words: a setting read as `undefined` behind a type
    // that says it is a number is the failure this exists to prevent, and a
    // message about the value would describe the symptom, not the file.
    expect(refusal(() => parseConfig(partial))).toContain('is missing "board_max"');
  });

  it('says what a setting should have been when it reads as something else', () => {
    const message = refusal(() => parseConfig(configYaml().replace('vote_window_days: 14', "vote_window_days: soon")));
    expect(message).toContain('"vote_window_days"');
    expect(message).toContain('whole number');
    expect(message).toContain('"soon"');
  });

  it('refuses an empty config rather than inventing one', () => {
    expect(refusal(() => parseConfig(''))).toContain('instance/data/config.yml');
    expect(refusal(() => parseConfig('- a\n- list\n'))).toContain('a list');
  });

  it('names the board member, and the value it could not read', () => {
    const message = refusal(() =>
      parseConfig(configYaml({ board: [{ login: 'alice', joined_on: '', status: 'active', unavailable_until: '' }] })
        .replace('status: active', 'status: away')),
    );
    expect(message).toContain('the board, board entry 1,');
    expect(message).toContain('"away"');
    expect(message).toContain('active, inactive');
  });

  it('names the nomination outcome vocabulary, blank included', () => {
    const message = refusal(() =>
      parseConfig(
        configYaml({
          nominations: [{ candidate: 'frank', sponsor: 'alice', opened_on: '', objections: [], outcome: '' }],
        }).replace("outcome: ''", 'outcome: rejected'),
      ),
    );
    expect(message).toContain('(blank)');
    expect(message).toContain('accepted, deferred, waiting');
  });

  it('reads the sla_days block, and says so by name when it is not a block', () => {
    // Only the block, not everything after it: `channels` sits below
    // `sla_days` in the file the app writes, and swallowing it would make
    // this test read a config missing a key instead of one whose block is
    // not a block.
    const text = configYaml().replace(/sla_days:[\s\S]*?(?=channels:)/, 'sla_days: 14\n');
    const message = refusal(() => parseConfig(text));
    expect(message).toContain('"sla_days"');
    expect(message).toContain('block of settings');
  });

  it('rejects a fractional window rather than rounding it behind the board', () => {
    expect(refusal(() => parseConfig(configYaml().replace('inactivity_months: 6', 'inactivity_months: 6.5'))))
      .toContain('whole number');
  });

  it('rejects an eligibility_share that is not a number', () => {
    const text = configYaml().replace(/eligibility_share: [^\n]+\n/, "eligibility_share: 'two thirds'\n");
    const message = refusal(() => parseConfig(text));
    expect(message).toContain('"eligibility_share"');
    expect(message).toContain(']0, 1]');
  });

  it('rejects an eligibility_share of zero, the excluded end of the range', () => {
    const text = configYaml().replace(/eligibility_share: [^\n]+\n/, 'eligibility_share: 0\n');
    expect(refusal(() => parseConfig(text))).toContain(']0, 1]');
  });

  it('rejects an eligibility_share above one', () => {
    const text = configYaml().replace(/eligibility_share: [^\n]+\n/, 'eligibility_share: 1.5\n');
    expect(refusal(() => parseConfig(text))).toContain(']0, 1]');
  });

  it('accepts an eligibility_share of exactly one, the included end of the range', () => {
    expect(parseConfig(configYaml({ eligibility_share: 1 })).eligibility_share).toBe(1);
  });
});

describe('what a volunteer is told when instance/data/speakers.yml is malformed', () => {
  it('points at the record by its id, not by counting down the file', () => {
    const message = refusal(() => parseSpeakers(speakersYaml([speaker(), speaker({ id: 'spk-042' })])
      .replace('status: lead\n  selection', 'status: postponed\n  selection')));
    expect(message).toContain('instance/data/speakers.yml');
    expect(message).toContain('speaker 1 (spk-001)');
    expect(message).toContain('"postponed"');
  });

  it('falls back to the position when even the id is unusable', () => {
    expect(refusal(() => parseSpeakers('- 42\n'))).toContain('speaker 1');
  });

  it('refuses a speakers file that is not a list of records', () => {
    expect(refusal(() => parseSpeakers('season: 2026\n'))).toContain('list of speakers');
  });

  it('names the ballot inside the record it belongs to', () => {
    const message = refusal(() =>
      parseSpeakers(
        speakersYaml([
          {
            selection: {
              ballots: [{ voter: 'alice', value: 'yes', comment: '', coi_reason: '', date: '' }],
              opened_on: '',
              decided_on: '',
            },
          },
        ]).replace("value: 'yes'", 'value: maybe'),
      ),
    );
    expect(message).toContain('selection, ballots entry 1,');
    expect(message).toContain('yes, abstain, recused');
  });

  it('keeps a metric that is null and refuses one that is neither number nor blank', () => {
    const kept = parseSpeakers(speakersYaml([{ metrics: { registrations: 0, live_peak: null, youtube_views_30d: null, forum_replies: null } }]));
    expect(kept[0].metrics.registrations).toBe(0);
    expect(kept[0].metrics.live_peak).toBeNull();
    expect(refusal(() => parseSpeakers(speakersYaml([{}]).replace('registrations: null', "registrations: many"))))
      .toContain('"registrations"');
  });

  it('refuses a runbook step that is neither ticked nor not', () => {
    const message = refusal(() =>
      parseSpeakers(speakersYaml([{ runbook_progress: { 'approved/invitation-sent': true } }])
        .replace('approved/invitation-sent: true', 'approved/invitation-sent: soon')),
    );
    expect(message).toContain('approved/invitation-sent');
    expect(message).toContain('yes or no');
  });

  it('refuses a link list that is not a list, and a link that is not text', () => {
    expect(refusal(() => parseSpeakers(speakersYaml([{}]).replace('links: []', 'links: one, two'))))
      .toContain('"links"');
    expect(refusal(() => parseSpeakers(speakersYaml([{ links: ['ok'] }]).replace('- ok', '- 12'))))
      .toContain('links entry 1');
  });

  it('refuses a record that is not a block at all', () => {
    expect(refusal(() => parseSpeakers('- - a\n  - b\n'))).toContain('block of settings');
  });

  it('says "an empty value" rather than printing null at a volunteer', () => {
    const message = refusal(() => parseSpeakers(speakersYaml([{}]).replace("name: A Speaker", 'name: null')));
    expect(message).toContain('an empty value');
  });

  it('says "an empty text" for a field that has to say something', () => {
    const message = refusal(() => parseSpeakers(speakersYaml([{}]).replace('gender: undisclosed', "gender: ''")));
    expect(message).toContain('an empty text');
  });
});

describe('the hand-edited fixture, read from both languages', () => {
  // tools/tests/governance/test_hand_edited.py reads these same two files and asserts
  // what `convener-validate` reports. Absent keys, unquoted scalars: what a file
  // typed into GitHub's web editor actually looks like.
  it('refuses the hand-typed speaker, naming it and the first field it lacks', () => {
    const message = refusal(() => parseSpeakers(fixture('hand-edited-speakers.yml')));
    expect(message).toContain('speaker 1 (spk-201)');
    expect(message).toContain('is missing "gender"');
  });

  it('refuses the config left behind by an earlier schema, naming the setting', () => {
    const message = refusal(() => parseConfig(fixture('hand-edited-config.yml')));
    expect(message).toContain('"vote_threshold"');
  });

  it('reads an unquoted 12:30 as text, exactly as the Python loader does', () => {
    // The browser's YAML reader is 1.2, so a bare `12:30` was never the
    // integer 750 here -- but the assertion belongs on this side too: it is
    // what makes the pair a contract rather than two habits, and the
    // narrowing would refuse a number where the model says text.
    expect(fixture('hand-edited-speakers.yml')).toContain('time: 12:30');
    const unquoted = speakersYaml([{ time: '12:30' }]).replace("time: '12:30'", 'time: 12:30');
    expect(parseSpeakers(unquoted)[0].time).toBe('12:30');
  });
});

describe('the config the tests themselves stand on', () => {
  it('is a config the reader accepts, so no test double is a shape the app forbids', () => {
    expect(parseConfig(configYaml())).toEqual(config());
    expect(parseSpeakers(speakersYaml([{}]))).toEqual([speaker()]);
  });
});

describe('the repository this app actually reads', () => {
  // The one assertion that would have caught every defect in this class
  // before a volunteer did: the real files, through the real reader. It
  // needs no network -- `instance/data/` is in the repository the tests run from --
  // and it fails the moment the model and the data part company, whichever
  // of the two moved.
  function dataFile(name: string): string {
    return readFileSync(resolve(__dirname, `../../instance/data/${name}`), 'utf-8');
  }

  // `parseSpeakers` throws on anything the model refuses -- a top level that
  // is not a list, a row missing a field, a value outside a closed
  // vocabulary -- so the call is the assertion, and it is the file itself
  // that is on trial rather than what happens to be in it.
  //
  // It used to open on `expect(speakers.length).toBeGreaterThan(0)`, as the
  // non-vacuity guard for the row assertion under it. The records were
  // cleared of personal data and the list became empty, so that
  // line would now pin this repository to holding rows -- and re-adding
  // records is an ordinary cockpit operation, not a repair. An empty list is
  // a shape the model has to accept. The check still fails on its own the
  // moment the file and the model part company, which is what it is for.
  it('reads instance/data/speakers.yml as the model says it is', () => {
    expect(() => parseSpeakers(dataFile('speakers.yml'))).not.toThrow();
    expect(parseSpeakers(dataFile('speakers.yml')).every(s => s.id !== '')).toBe(true);
  });

  it('reads instance/data/config.yml as the model says it is', () => {
    const cfg = parseConfig(dataFile('config.yml'));
    expect(cfg.board.length).toBeGreaterThan(0);
    expect(cfg.sla_days.invitation_follow_up).toBeGreaterThan(0);
    // The board's decision deadline is this one and no other.
    expect(cfg.vote_window_days).toBeGreaterThan(0);
  });
});
