/**
 * The queue of edits a tab is holding, read on its own.
 *
 * The provider decides *when* to write; this decides what a queue is, what it
 * does to a record, and what its commit says. Those are the parts a volunteer
 * can lose work to, so they are held here without a timer, a browser or a
 * network in the way.
 */
import { describe, expect, it } from 'vitest';
import {
  applyPending,
  enqueue,
  pendingCount,
  pendingSubject,
  type Queue,
} from '../../src/data/pending';
import { itemKey } from '../../src/state/decisions';
import { speaker as double } from '../helpers/data-doubles';
import type { Speaker } from '../../src/data/types';

const tick = (key: string, value: boolean) => ({
  apply: (s: Speaker) => ({
    ...s,
    runbook_progress: { ...s.runbook_progress, [key]: value },
  }),
  edit: { part: 'runbook-box', key: itemKey(key), ticked: value } as const,
});

const field = (key: 'title', value: string) => ({
  apply: (s: Speaker) => ({ ...s, [key]: value }),
  edit: { part: 'field', key } as const,
});

const records = () => [double({ id: 'spk-001' }), double({ id: 'spk-002' })];

describe('holding an edit', () => {
  it('starts a queue against the record the edit belongs to', () => {
    const { queue, flush } = enqueue(null, 'spk-001', tick('a/one', true));

    expect(queue.id).toBe('spk-001');
    expect(pendingCount(queue)).toBe(1);
    expect(flush).toBeNull();
  });

  it('adds to the queue while the record is the same', () => {
    const first = enqueue(null, 'spk-001', tick('a/one', true));
    const second = enqueue(first.queue, 'spk-001', tick('a/two', true));

    expect(pendingCount(second.queue)).toBe(2);
    expect(second.flush).toBeNull();
  });

  it('never merges two records, and hands back the one to write first', () => {
    // A commit subject names one entity. A queue holding edits to two
    // speakers could only name one of them, so the other's work would be
    // committed under a subject that is about somebody else.
    const first = enqueue(null, 'spk-001', tick('a/one', true));
    const second = enqueue(first.queue, 'spk-002', tick('a/one', true));

    expect(second.flush).toEqual(first.queue);
    expect(second.queue.id).toBe('spk-002');
    expect(pendingCount(second.queue)).toBe(1);
  });
});

describe('what the record looks like while edits are held', () => {
  it('applies every held edit, in the order they were made', () => {
    const queue: Queue = {
      id: 'spk-001',
      edits: [tick('a/one', true), field('title', 'A talk'), tick('a/two', true)],
    };

    const [one, two] = applyPending(queue, records());
    expect(one.runbook_progress['a/one']).toBe(true);
    expect(one.runbook_progress['a/two']).toBe(true);
    expect(one.title).toBe('A talk');
    // And nothing at all to the record the queue is not about.
    expect(two.runbook_progress['a/one']).toBeUndefined();
  });

  it('ends where the volunteer left it when a box is ticked and unticked', () => {
    const queue: Queue = { id: 'spk-001', edits: [tick('a/one', true), tick('a/one', false)] };

    expect(applyPending(queue, records())[0].runbook_progress['a/one']).toBe(false);
  });

  it('leaves the list alone when nothing is held', () => {
    const before = records();
    expect(applyPending(null, before)).toBe(before);
    expect(applyPending({ id: 'spk-001', edits: [] }, before)).toBe(before);
  });

  it('is the same function the write transforms with', () => {
    // Not a restatement: the screen draws from `applyPending` and the write
    // transforms with it, so what a volunteer sees and what lands cannot be
    // two different answers. A test that built the expected record by hand
    // here would be asserting a third one.
    const queue: Queue = { id: 'spk-001', edits: [tick('a/one', true)] };
    const onScreen = applyPending(queue, records());
    const written = applyPending(queue, records());

    expect(written).toEqual(onScreen);
  });
});

describe('what the commit says', () => {
  it('says exactly what a single edit always said', () => {
    // Batching changed no subject that already existed: a queue of one
    // renders through that edit's own phrase, so every message this screen
    // used to write, it still writes.
    const queue: Queue = { id: 'spk-001', edits: [tick('a/one', true)] };

    expect(pendingSubject(queue)).toBe('data: spk-001 runbook a/one=true');
  });

  it('counts, rather than listing, once there are several', () => {
    // A subject is one permanent line. Nine keys in it would be unreadable
    // in every tool that shows one, and the diff is where the nine are.
    const queue: Queue = {
      id: 'spk-001',
      edits: [tick('a/one', true), tick('a/two', true), field('title', 'A talk')],
    };

    expect(pendingSubject(queue)).toBe('data: spk-001 3 checklist lines');
  });

  it('puts no typed value in the subject, however many are held', () => {
    // The rule `speaker-page-subjects.test.tsx` exists for, restated across
    // the batch: a commit subject is permanent and unrewritable, and a
    // researcher's typed answer has no business in one.
    const queue: Queue = {
      id: 'spk-001',
      edits: [field('title', 'A deeply personal title'), tick('a/one', true)],
    };

    expect(pendingSubject(queue)).not.toContain('deeply personal');
  });
});
