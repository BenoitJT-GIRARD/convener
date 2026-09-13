import { readFileSync, readdirSync, statSync } from 'node:fs';
import { CANCELLATION_REASONS } from '../../src/state/transitions';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import cases from '../../../tools/tests/fixtures/governance-cases.json';
import {
  ACTS,
  formatDecision,
  identifier,
  isIdentifier,
  DecisionRejected,
  dataEdit,
  isSubject,
  itemKey,
  transitionDecision,
  type Edit,
  type Decision,
  type DecisionKind,
  type PlainDecisionKind,
} from '../../src/state/decisions';
import type { Transition } from '../../src/state/transitions';
import type { FieldKey } from '../../src/state/phases';
import {
  BALLOT_VALUES,
  CONSENT_DECISIONS,
  OBJECTION_RESOLUTIONS,
  isBallotValue,
  type ConsentDecision,
  type ObjectionResolution,
  type SpeakerStatus,
} from '../../src/data/types';

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
    case 'cancel-edition': {
      const reason = CANCELLATION_REASONS.find(r => r === detail);
      if (!reason) throw new Error(`not a cancellation reason: ${detail}`);
      return { kind: 'cancel-edition', entity, actor, detail: reason };
    }
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
    // `tools/convener_ops/governance/commit_format.py` holds the same table; the fixture
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
      'mark-delivered',
      'finalize-archive',
      'archive-unpublished',
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
    // The same table `tools/tests/governance/test_commit_format.py` reads. `_TOKEN`
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

  it('is the only place in the app a `data:` or `config:` subject is assembled', () => {
    // The eight ad-hoc template literals this replaced were not caught by
    // anything: none of them opened with an act phrase, so `_claimed_kind`
    // returned nothing and `convener-check-commits` passed them in silence. One
    // carried a researcher's full name. A subject built anywhere else is
    // therefore invisible until it is in the history for good, which is why
    // the rule is checked over the source rather than over the messages.
    const root = join(__dirname, '../..', 'src');
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
        // Any quote, and no space required: the defect is a subject
        // assembled outside this module, not the one spelling of it the
        // guard was first written against. A backtick-only pattern let
        // `'data: add lead ' + fields.name` through, and a split template
        // (`` `data:` `` then the rest) with it.
        //
        // `config:` joined `data:` when the settings
        // screen gained a domain of its own: those commits change a
        // threshold in a declaration, name no record and no person, and are
        // deliberately not decisions -- but they are still permanent
        // subjects, so they are assembled in exactly one place too.
        .filter(l => /[`'"](?:data|config):/.test(l.text)),
    );
    expect(subjects.map(s => `${s.file}:${s.line}`)).toHaveLength(3);
    for (const s of subjects) expect(s.file).toMatch(/decisions\.ts$/);
  });

  it('writes a non-decision subject about the record and nobody else', () => {
    expect(dataEdit(identifier('spk-001'), { part: 'field', key: 'title' })).toBe(
      'data: spk-001 set title',
    );
    // The same `Identifier` gate as the register: a person cannot be named
    // in one of these either.
    expect(() => dataEdit(identifier('Jane Doe'), { part: 'field', key: 'title' })).toThrow(
      DecisionRejected,
    );
  });

  it('has no slot for a field value in a bookkeeping subject', () => {
    // The defect this closes: `set ${k}` widened to `set ${k}=${v}` put a
    // researcher's typed answer into a permanent commit subject and left
    // every test green, because `what` was a bare `string` with a doc
    // comment asking callers not to. `Edit` names the part that moved and
    // has nowhere to put what was written on it.
    const edits: Edit[] = [
      { part: 'admin-fields' },
      { part: 'post-archive-metrics' },
      { part: 'field', key: 'title' },
      { part: 'runbook-box', key: itemKey('approved/invitation-sent'), ticked: true },
      { part: 'owner', key: itemKey('scheduled/T-30/visuals'), cleared: false },
      { part: 'owner', key: itemKey('scheduled/T-30/visuals'), cleared: true },
    ];
    // Every phrase the five parts can render is one the other language
    // already reads back as bookkeeping. A reword on either side fails here.
    const ordinary = new Set(cases.commit_message_ordinary.map(c => c.message));
    for (const edit of edits) {
      expect(ordinary, JSON.stringify(edit)).toContain(dataEdit(identifier('spk-001'), edit));
    }
  });

  it('reads back every line it can write, and nothing else', () => {
    // The check `mutate` makes of the string itself, at the last point
    // before a subject is permanent. The brand is a compile-time fact -- a
    // cast is past it, and an `any` is past it without a cast -- and the
    // source walk reads text, so a prefix assembled out of pieces is past
    // that. This one is asked of what is actually about to be committed.
    for (const c of cases.commit_message_cases) {
      expect(isSubject(c.message as string), c.name as string).toBe(true);
    }
    for (const c of cases.commit_message_ordinary) {
      const message = c.message as string;
      // The bookkeeping subjects this module writes are in that fixture
      // alongside commits it has nothing to do with (`app:`, `docs:`, the
      // form intake, the nightly sweep), which it must not claim.
      expect(isSubject(message), c.name as string).toBe(
        message.startsWith('data: spk-001 '),
      );
    }
    expect(isSubject('data: add lead Jane Doe')).toBe(false);
    expect(isSubject('data: spk-001 set title=Jane Doe')).toBe(false);
    expect(isSubject('data: spk-001 admin edit by mallory')).toBe(false);
  });

  it('refuses a field name cast into carrying its own value', () => {
    // The union is the control and the cast is the way past it, so the key
    // is checked as well as typed. `set title=Jane Doe` in a permanent
    // subject is the whole finding, one level down from the entity.
    expect(() =>
      dataEdit(identifier('spk-001'), { part: 'field', key: 'title=Jane Doe' as FieldKey }),
    ).toThrow(DecisionRejected);
  });

  it('refuses a journey key that is a sentence about a person', () => {
    // The one place an `Edit` takes a string: the runbook key comes off a
    // DOM event, so it is checked rather than trusted. A value carries
    // spaces, an `=`, or punctuation; a key does not.
    expect(itemKey('promotion/forum')).toBe('promotion/forum');
    expect(itemKey('scheduled/T-30/visuals')).toBe('scheduled/T-30/visuals');
    for (const bad of ['title=Jane Doe', 'Jane Doe (CNRS)', 'set title=x', '', 'a b']) {
      expect(() => itemKey(bad), bad).toThrow(DecisionRejected);
    }
  });
});
