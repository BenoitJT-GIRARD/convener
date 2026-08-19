/**
 * A named owner on one line of the journey.
 *
 * The first block is the reason this module exists at all, and it is written
 * two ways on purpose: once as the case anybody would think of (a lead owner
 * present, an item owner absent), and once as a rule over the source of
 * `state/assignment.ts` itself. The first would pass again the day somebody
 * adds `?? speaker.host_1`; the second would not, and neither would any other
 * fallback to a name field the record already holds. Phase 2 lost the record
 * of who had to write to a declined speaker because two notions shared one
 * field, so the guarantee here is that the derivation cannot be written, not
 * that one particular derivation was tried and found absent.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect } from 'vitest';
import {
  AssignmentRejected,
  assignItem,
  itemAssignee,
  itemsWaitingFor,
  unassignItem,
} from '../src/state/assignment';
import { PHASES } from '../src/state/phases';
import { config, speaker, speakersYaml } from './data-doubles';
import { parseSpeakers } from '../src/data/yaml';
import cases from '../../tools/tests/fixtures/governance-cases.json';

const VISUALS = 'scheduled/T-30/visuals';
const LINKEDIN = 'scheduled/T-21/linkedin';
const SUMMARY = 'delivered/forum-summary';
/** A line of the journey that does not exist in `state/phases.ts`: it comes
 *  from the channel list in `data/config.yml`, through `state/channels.ts`. */
const CHANNEL = 'promotion/forum';

/** A scheduled talk, the phase whose lines are the ones volunteers divide up. */
function scheduled(overrides: Parameters<typeof speaker>[0] = {}) {
  return speaker({ id: 'spk-001', status: 'scheduled', date: '2026-09-01', ...overrides });
}

describe('an item owner is never derived from the lead owner', () => {
  it('never derives an item assignee from the lead owner', () => {
    const s = { ...speaker(), assigned_to: 'ada', checklist: {} };
    expect(itemAssignee(s, VISUALS)).toBe('');
  });

  it('reads no name off the record other than the one put against the line', () => {
    const s = speaker({
      assigned_to: 'ada',
      proposed_by: 'Professor Somebody',
      host_1: 'bob',
      host_2: 'carol',
      checklist: {},
    });
    for (const phase of PHASES) {
      for (const item of phase.items) {
        expect(itemAssignee(s, item.key)).toBe('');
      }
    }
  });

  it('keeps the lead owner and the item owner apart when both are set', () => {
    const s = speaker({ assigned_to: 'ada', checklist: { [VISUALS]: { assignee: 'bob' } } });
    expect(s.assigned_to).toBe('ada');
    expect(itemAssignee(s, VISUALS)).toBe('bob');
  });

  it('leaves the lead owner untouched when a line is assigned', () => {
    const s = speaker({ assigned_to: 'ada', proposed_by: 'Professor Somebody' });
    const [after] = assignItem([s], 'spk-001', VISUALS, 'bob', null);
    expect(after.assigned_to).toBe('ada');
    expect(after.proposed_by).toBe('Professor Somebody');
  });

  /**
   * The structural half. `state/assignment.ts` explains the distinction in its
   * comments -- so the comments are stripped and the *code* is read: no
   * fallback to any of the four name fields the record carries can be written
   * here without turning this red, including one nobody has thought of yet.
   */
  it('does not name any other field of the record in its code', () => {
    const source = readFileSync(resolve(__dirname, '../src/state/assignment.ts'), 'utf-8');
    const code = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
    for (const field of ['assigned_to', 'proposed_by', 'host_1', 'host_2']) {
      expect(code).not.toContain(field);
    }
    // The stripping itself has to be doing something, or the assertion above
    // would pass on an empty string.
    expect(code).toContain('speaker.checklist[itemKey]');
  });
});

describe('no owner is the normal state', () => {
  it('reads an absent entry and a blank name as the same fact', () => {
    const absent = speaker({ checklist: {} });
    const blank = speaker({ checklist: { [VISUALS]: { assignee: '' } } });
    expect(itemAssignee(absent, VISUALS)).toBe('');
    expect(itemAssignee(blank, VISUALS)).toBe('');
  });

  it('waits for nobody when nobody is signed in', () => {
    const s = scheduled({ checklist: { [VISUALS]: { assignee: 'bob' } } });
    expect(itemsWaitingFor([s], null, null)).toEqual([]);
    expect(itemsWaitingFor([s], '', null)).toEqual([]);
  });

  it('raises nothing at all for a record nobody is down for', () => {
    const s = scheduled();
    expect(itemsWaitingFor([s], 'bob', null)).toEqual([]);
    expect(itemsWaitingFor([s], 'ada', null)).toEqual([]);
  });

  it('stores no blank owner: assigning nobody removes the entry', () => {
    const s = speaker({ checklist: { [VISUALS]: { assignee: 'bob' } } });
    const [cleared] = assignItem([s], 'spk-001', VISUALS, '', null);
    expect(cleared.checklist).toEqual({});
    const [unassigned] = unassignItem([s], 'spk-001', VISUALS, null);
    expect(unassigned.checklist).toEqual({});
  });
});

describe('writing an owner', () => {
  it('writes only the record asked for, and only the line asked for', () => {
    const a = speaker({ id: 'spk-001', checklist: { [SUMMARY]: { assignee: 'carol' } } });
    const b = speaker({ id: 'spk-002' });
    const after = assignItem([a, b], 'spk-001', VISUALS, 'bob', null);
    expect(after[0].checklist).toEqual({
      [SUMMARY]: { assignee: 'carol' },
      [VISUALS]: { assignee: 'bob' },
    });
    expect(after[1].checklist).toEqual({});
  });

  it('reads the list it is given, so it can be replayed by mutate', () => {
    const rendered = [speaker({ id: 'spk-001', checklist: {} })];
    const fresh = [speaker({ id: 'spk-001', checklist: { [SUMMARY]: { assignee: 'carol' } } })];
    // The transformation is built against `rendered` and applied to `fresh`:
    // an owner recorded meanwhile has to survive.
    const transform = (current: typeof rendered) =>
      assignItem(current, 'spk-001', VISUALS, 'bob', null);
    expect(transform(rendered)[0].checklist).toEqual({ [VISUALS]: { assignee: 'bob' } });
    expect(transform(fresh)[0].checklist).toEqual({
      [SUMMARY]: { assignee: 'carol' },
      [VISUALS]: { assignee: 'bob' },
    });
  });

  it('does not mutate the record it was given', () => {
    const s = speaker({ checklist: {} });
    assignItem([s], 'spk-001', VISUALS, 'bob', null);
    expect(s.checklist).toEqual({});
  });

  it('trims the name, so a stray space is not a second person', () => {
    const [after] = assignItem([speaker()], 'spk-001', VISUALS, '  bob  ', null);
    expect(itemAssignee(after, VISUALS)).toBe('bob');
  });

  it('puts an owner on a promotion channel, which is a line of the journey too', () => {
    // The blocker Task 6 left behind: the channel list is configuration, and
    // a guard that only knew the static table refused every one of its keys.
    const [after] = assignItem([scheduled()], 'spk-001', CHANNEL, 'bob', config());
    expect(itemAssignee(after, CHANNEL)).toBe('bob');
  });

  it('follows the file rather than a remembered list of channels', () => {
    const cfg = config({ channels: [{ key: 'posters', label: 'Printed posters' }] });
    const [after] = assignItem([scheduled()], 'spk-001', 'promotion/posters', 'bob', cfg);
    expect(itemAssignee(after, 'promotion/posters')).toBe('bob');
    // `forum` is in the double's default list and not in this one. A guard
    // reading a constant would have accepted it here.
    expect(() => assignItem([scheduled()], 'spk-001', CHANNEL, 'bob', cfg)).toThrow(
      AssignmentRejected,
    );
  });

  it('refuses a line the journey does not have', () => {
    expect(() => assignItem([speaker()], 'spk-001', 'made/up/step', 'bob', null)).toThrow(
      AssignmentRejected,
    );
    expect(() => unassignItem([speaker()], 'spk-001', 'made/up/step', null)).toThrow(
      AssignmentRejected,
    );
  });
});

describe('what is waiting for me', () => {
  it('lists the outstanding lines this person is down for', () => {
    const s = scheduled({
      checklist: { [VISUALS]: { assignee: 'bob' }, [LINKEDIN]: { assignee: 'carol' } },
    });
    expect(itemsWaitingFor([s], 'bob', null).map(w => w.item.key)).toEqual([VISUALS]);
    expect(itemsWaitingFor([s], 'carol', null).map(w => w.item.key)).toEqual([LINKEDIN]);
  });

  it('raises an unticked channel for whoever is down for it', () => {
    const s = scheduled({ checklist: { [CHANNEL]: { assignee: 'bob' } } });
    expect(itemsWaitingFor([s], 'bob', config()).map(w => w.item.key)).toEqual([CHANNEL]);
    // Without a config there is no channel list to expand, so the journey
    // reads as the static table and this line is not in it.
    expect(itemsWaitingFor([s], 'bob', null)).toEqual([]);
  });

  it('drops a line as soon as it is done, rather than nagging about it', () => {
    const s = scheduled({
      checklist: { [VISUALS]: { assignee: 'bob' } },
      runbook_progress: { [VISUALS]: true },
    });
    expect(itemsWaitingFor([s], 'bob', null)).toEqual([]);
  });

  it('reads a required field as done once it carries a value', () => {
    const base = {
      status: 'delivered' as const,
      date: '2026-05-01',
      checklist: { 'delivered/registrations': { assignee: 'bob' } },
    };
    const empty = speaker(base);
    const filled = speaker({
      ...base,
      metrics: { registrations: 40, live_peak: null, youtube_views_30d: null, forum_replies: null },
    });
    expect(itemsWaitingFor([empty], 'bob', null).map(w => w.item.key)).toEqual([
      'delivered/registrations',
    ]);
    expect(itemsWaitingFor([filled], 'bob', null)).toEqual([]);
  });

  it('leaves behind a name on a line the event has already moved past', () => {
    // The visual was somebody's job while the talk was scheduled. Once it is
    // delivered, that line is history: raising it again would be the nag this
    // feature is meant not to become.
    const s = speaker({
      status: 'delivered',
      date: '2026-05-01',
      checklist: { [VISUALS]: { assignee: 'bob' } },
    });
    expect(itemsWaitingFor([s], 'bob', null)).toEqual([]);
  });

  it('says nothing about a record that has no journey left', () => {
    for (const status of ['archived', 'parked', 'decline-board'] as const) {
      const s = speaker({ status, checklist: { [VISUALS]: { assignee: 'bob' } } });
      expect(itemsWaitingFor([s], 'bob', null)).toEqual([]);
    }
  });

  it('carries the record alongside the line, so the screen can link to it', () => {
    const s = scheduled({ checklist: { [VISUALS]: { assignee: 'bob' } } });
    const [waiting] = itemsWaitingFor([s], 'bob', null);
    expect(waiting.speaker.id).toBe('spk-001');
    expect(waiting.item.label).toBe('Visuals + flyer made');
  });

  it('describes work, never a person', () => {
    // The row a volunteer reads is the item's own label, fixed in
    // `state/phases.ts`, and the lateness sentence beside it comes from
    // `state/sla.ts`. Neither has a slot for a name, and neither is written
    // here -- so the six words the inactivity sweep bans have nowhere to enter.
    const s = scheduled({ checklist: { [VISUALS]: { assignee: 'bob' } } });
    for (const w of itemsWaitingFor([s], 'bob', null)) {
      expect(w.item.label).not.toContain('bob');
    }
  });
});

/**
 * Who may be named against a line, in both languages.
 *
 * `tools/convener_ops/validate.py` refused an assignee that is not a GitHub login;
 * this side accepted any string, in the file reader and in `assignItem`
 * alike. The `<select>` of board logins on the speaker page is a screen, not
 * a rule -- `assignItem` is exported, and a hand-edited file goes through the
 * reader and nothing else -- so the browser could accept and write a record
 * `convener-validate` then refuses. `tools/tests/test_validate_v4.py` runs these
 * same cases through the other reader.
 */
describe('the shared statement of who can own a line', () => {
  it.each(cases.checklist_assignee_cases)('$name -- the writer', c => {
    const call = () => assignItem([scheduled()], 'spk-001', VISUALS, c.login, config());
    if (c.valid) {
      expect(call()[0].checklist[VISUALS]).toEqual({ assignee: c.login });
    } else {
      expect(call).toThrow(AssignmentRejected);
    }
  });

  it.each(cases.checklist_assignee_cases)('$name -- the file reader', c => {
    const yaml = speakersYaml([{ checklist: { [VISUALS]: { assignee: c.login } } }]);
    if (c.valid) {
      expect(parseSpeakers(yaml)[0].checklist[VISUALS]).toEqual({ assignee: c.login });
    } else {
      expect(() => parseSpeakers(yaml)).toThrow(/not a GitHub username/);
    }
  });

  it('leaves "nobody" alone, which is what most lines say', () => {
    // `''` is not one of the cases above: it is the answer "the hosts", legal
    // on both sides, and `assignItem` spells it by removing the entry.
    const s = assignItem([scheduled()], 'spk-001', VISUALS, '   ', config());
    expect(s[0].checklist[VISUALS]).toBeUndefined();
    expect(parseSpeakers(speakersYaml([{ checklist: { [VISUALS]: { assignee: '' } } }]))[0]
      .checklist[VISUALS]).toEqual({ assignee: '' });
  });
});
