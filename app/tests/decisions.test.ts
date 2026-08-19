import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import cases from '../../tools/tests/fixtures/governance-cases.json';
import {
  ACTS,
  formatDecision,
  identifier,
  isIdentifier,
  DecisionRejected,
  dataEdit,
  transitionDecision,
  type Decision,
  type DecisionKind,
  type PlainDecisionKind,
} from '../src/state/decisions';
import type { Transition } from '../src/state/transitions';
import {
  BALLOT_VALUES,
  CONSENT_DECISIONS,
  OBJECTION_RESOLUTIONS,
  isBallotValue,
  type ConsentDecision,
  type ObjectionResolution,
  type SpeakerStatus,
} from '../src/data/types';

const STATUSES: readonly SpeakerStatus[] = [
  'lead',
  'approved',
  'invited',
  'confirmed',
  'scheduled',
  'delivered',
  'archived',
  'parked',
  'decline-board',
  'decline-speaker',
];

interface FixtureCase {
  name: string;
  kind: string;
  entity: string;
  actor: string;
  detail: string;
}

/** The fixture is JSON, so every field arrives as a bare string. Narrowing it
 *  through the same unions the app writes with means a typo in the shared
 *  fixture fails here rather than producing a line neither side can read. */
function decisionFrom(c: FixtureCase): Decision {
  const entity = identifier(c.entity);
  const actor = identifier(c.actor);
  const { detail } = c;
  switch (c.kind) {
    case 'availability-set':
      if (detail !== 'away' && detail !== 'back') {
        throw new Error(`not an availability change: ${detail}`);
      }
      return { kind: 'availability-set', entity, actor, detail };
    case 'ballot-cast':
      if (!isBallotValue(detail)) throw new Error(`not a ballot value: ${detail}`);
      return { kind: 'ballot-cast', entity, actor, detail };
    case 'consent-set':
      if (!(CONSENT_DECISIONS as readonly string[]).includes(detail)) {
        throw new Error(`not a consent decision: ${detail}`);
      }
      return { kind: 'consent-set', entity, actor, detail: detail as ConsentDecision };
    case 'publication-resolve':
      if (!(OBJECTION_RESOLUTIONS as readonly string[]).includes(detail)) {
        throw new Error(`not a resolution: ${detail}`);
      }
      return {
        kind: 'publication-resolve',
        entity,
        actor,
        detail: detail as ObjectionResolution,
      };
    case 'date-answer':
      if (detail !== 'accepted' && detail !== 'declined' && detail !== 'cleared') {
        throw new Error(`not a date reply: ${detail}`);
      }
      return { kind: 'date-answer', entity, actor, detail };
    case 'override': {
      const status = STATUSES.find(s => s === detail);
      if (!status) throw new Error(`not a speaker status: ${detail}`);
      return { kind: 'override', entity, actor, detail: status };
    }
    default: {
      if (!(c.kind in ACTS)) throw new Error(`unknown decision kind: ${c.kind}`);
      if (detail !== '') throw new Error(`${c.kind} takes no qualifier`);
      return { kind: c.kind as PlainDecisionKind, entity, actor };
    }
  }
}

describe('the grammar of decision commits', () => {
  it.each(cases.commit_message_cases)('$name', c => {
    expect(formatDecision(decisionFrom(c))).toBe(c.message);
  });

  it('writes every act it declares, and declares every act it writes', () => {
    // `tools/convener_ops/commit_format.py` holds the same table; the fixture
    // above is what stops the two drifting.
    const written = new Set(cases.commit_message_cases.map(c => c.kind));
    expect([...Object.keys(ACTS)].sort()).toEqual([...written].sort());
  });

  it('takes the ballot value from the ballot actually cast', () => {
    for (const value of BALLOT_VALUES) {
      const d = transitionDecision('ballot-cast', identifier('spk-007'), identifier('ada'), {
        value,
        comment: '',
        coiReason: value === 'recused' ? 'co-author' : '',
      });
      expect(formatDecision(d)).toBe(`data: record a ballot on spk-007 by ada (${value})`);
    }
  });

  it('takes the consent answer and the resolution from their payloads', () => {
    expect(
      formatDecision(transitionDecision('consent-set', identifier('spk-009'), identifier('ada'), {
        consent: 'refused',
      })),
    ).toBe('data: record the recording consent of spk-009 by ada (refused)');
    expect(
      formatDecision(
        transitionDecision('publication-resolve', identifier('spk-009'), identifier('ada'), {
          resolution: 'withhold',
          note: 'the speaker asked',
        }),
      ),
    ).toBe('data: resolve the objections on spk-009 by ada (withhold)');
    expect(
      formatDecision(
        transitionDecision('override', identifier('spk-005'), identifier('ada'), {
          status: 'decline-board',
        }),
      ),
    ).toBe('data: override the status of spk-005 by ada (decline-board)');
  });

  it('has a sentence for every transition the app can apply', () => {
    // A transition added without a line here would fall through to a message
    // the register cannot read -- so it cannot be added without one.
    const transitions: Transition[] = [
      'ballot-cast',
      'ballot-withdraw',
      'lead-park',
      'lead-decline',
      'reactivate',
      'send-invitation',
      'invited-accept',
      'invited-decline',
      'lock-date',
      'finalize-archive',
      'consent-set',
      'publication-approve',
      'publication-object',
      'publication-resolve',
      'vote-reopen',
      'override',
    ];
    for (const t of transitions) {
      expect(ACTS[t as DecisionKind]).toBeTruthy();
    }
  });

  it('never lets a qualifier out on an act that has none', () => {
    const parked = transitionDecision('lead-park', identifier('spk-003'), identifier('ada'));
    expect('detail' in parked).toBe(false);
    expect(formatDecision(parked)).toBe('data: park spk-003 by ada');
  });

  it('says nothing about the person, only about the record', () => {
    // The delete button knows the speaker's name; the subject line does not
    // carry it. Nothing in the vocabulary can be said about a volunteer.
    const line = formatDecision({
      kind: 'speaker-delete',
      entity: identifier('spk-005'),
      actor: identifier('ada'),
    });
    expect(line).toBe('data: delete the record of spk-005 by ada');
    for (const act of Object.values(ACTS)) {
      expect(act).toMatch(/^[a-z][a-z ]*$/);
    }
  });

  it.each(cases.identifier_cases)('$name', c => {
    // The same table `tools/tests/test_commit_format.py` reads. `_TOKEN`
    // there and `TOKEN` here are one rule about what a commit subject may
    // point at, and this is what stops them drifting.
    expect(isIdentifier(c.value)).toBe(c.identifier);
  });

  it('cannot be given a person by name', () => {
    // The defect this closes: a free-text nomination candidate produced
    // `data: open a nomination for Jane Doe (CNRS) by ada`. That put a real
    // person's name into a history nothing rewrites, and `parse_decision`
    // then dropped the row, so the register lost the decision too.
    expect(() => identifier('Jane Doe (CNRS)')).toThrow(DecisionRejected);
    for (const c of cases.identifier_cases.filter(x => !x.identifier)) {
      expect(() => identifier(c.value), c.name).toThrow(DecisionRejected);
    }
  });

  it('says what to do instead, in a sentence a volunteer can act on', () => {
    let message = '';
    try {
      identifier('Jane Doe (CNRS)');
    } catch (e) {
      message = (e as Error).message;
    }
    expect(message).toContain('is not an identifier');
    expect(message).toContain('GitHub username');
    expect(message).not.toMatch(/regex|token|TOKEN|\/\^/);
  });

  it('is the only place in the app a `data:` subject is assembled', () => {
    // The eight ad-hoc template literals this replaced were not caught by
    // anything: none of them opened with an act phrase, so `_claimed_kind`
    // returned nothing and `convener-check-commits` passed them in silence. One
    // carried a researcher's full name. A subject built anywhere else is
    // therefore invisible until it is in the history for good, which is why
    // the rule is checked over the source rather than over the messages.
    const root = join(__dirname, '..', 'src');
    const files: string[] = [];
    const walk = (dir: string) => {
      for (const entry of readdirSync(dir)) {
        const full = join(dir, entry);
        if (statSync(full).isDirectory()) walk(full);
        else if (/\.tsx?$/.test(entry)) files.push(full);
      }
    };
    walk(root);
    const subjects = files.flatMap(f =>
      readFileSync(f, 'utf8')
        .split('\n')
        .map((text, i) => ({ file: f, line: i + 1, text }))
        // Code, not the comments that quote a subject to explain it.
        .filter(l => !/^\s*(\/\/|\*|\/\*)/.test(l.text))
        .filter(l => /`data: /.test(l.text)),
    );
    expect(subjects.map(s => `${s.file}:${s.line}`)).toHaveLength(2);
    for (const s of subjects) expect(s.file).toMatch(/decisions\.ts$/);
  });

  it('writes a non-decision subject about the record and nobody else', () => {
    expect(dataEdit(identifier('spk-001'), 'set title')).toBe('data: spk-001 set title');
    // The same `Identifier` gate as the register: a person cannot be named
    // in one of these either.
    expect(() => dataEdit(identifier('Jane Doe'), 'set title')).toThrow(DecisionRejected);
  });
});
