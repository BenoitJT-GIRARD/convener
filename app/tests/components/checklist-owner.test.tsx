/**
 * The owner control on a journey line, as a volunteer meets it.
 *
 * The screen half of `assignment.test.ts`. What is asserted here is mostly
 * what is *absent*: an unowned line carries no warning, no asterisk, no count
 * of what nobody has claimed, and no sentence about anybody. Not naming an
 * owner is what this series has always done, and a tool that scolds unpaid
 * volunteers over a field they never asked for is a tool they stop opening.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AuthProvider } from '../../src/auth/AuthContext';
import { Checklist } from '../../src/components/Checklist';
import { deriveInbox } from '../../src/state/inbox';
import { speaker, config } from '../helpers/data-doubles';

const VISUALS = 'scheduled/T-30/visuals';

function scheduled(checklist: Record<string, { assignee: string }> = {}) {
  return speaker({ status: 'scheduled', date: '2026-09-01', checklist });
}

function renderChecklist(
  s = scheduled(),
  onAssign: (key: string, login: string) => void = () => {},
) {
  render(
    <Checklist
      speaker={s}
      onToggle={() => {}}
      onField={() => {}}
      onAssign={onAssign}
      people={['ada', 'bob']}
      today="2026-08-20"
    />,
  );
}

describe('the owner of a journey line', () => {
  it('reads as the standing arrangement until somebody is named', () => {
    renderChecklist();
    const owners = screen.getAllByRole('combobox');
    expect(owners.length).toBeGreaterThan(0);
    for (const owner of owners) {
      expect((owner as HTMLSelectElement).value).toBe('');
    }
    expect(screen.getAllByText('the hosts, unless someone else takes it').length).toBe(
      owners.length,
    );
  });

  it.each([
    // `approved` holds one of each: two fields that already name whoever
    // does the thing, and one template somebody sends.
    ['approved' as const, 1],
    // `lead` holds the acknowledgement, which is a task, beside *Selection
    // criteria*, which is a page the board reads to make up its mind.
    ['lead' as const, 1],
  ])('draws the control on the tasks of %s, and on nothing else', (status, expected) => {
    render(
      <AuthProvider>
        <Checklist
          speaker={speaker({ status })}
          onToggle={() => {}}
          onField={() => {}}
          onAssign={() => {}}
          people={['ada']}
          today="2026-08-20"
        />
      </AuthProvider>,
    );
    expect(screen.getAllByRole('combobox')).toHaveLength(expected);
  });

  it('says nothing judgemental about a line nobody has taken', () => {
    renderChecklist();
    const page = document.body.textContent ?? '';
    for (const word of [
      'unassigned',
      'missing',
      'overdue',
      'failed',
      'late',
      'nobody has',
      'required',
    ]) {
      expect(page.toLowerCase()).not.toContain(word);
    }
  });

  it('shows the name that is on the record, and only from the record', () => {
    // `assigned_to` is a board member on this record and appears nowhere in
    // the owner control: the two are different notions, and the screen reads
    // the item's own owner or nothing.
    const s = speaker({
      status: 'scheduled',
      date: '2026-09-01',
      assigned_to: 'ada',
      checklist: { [VISUALS]: { assignee: 'bob' } },
    });
    renderChecklist(s);
    const values = screen.getAllByRole('combobox').map(o => (o as HTMLSelectElement).value);
    expect(values.filter(v => v === 'bob')).toHaveLength(1);
    expect(values.filter(v => v === 'ada')).toHaveLength(0);
  });

  it('records the person chosen against the line they were chosen for', () => {
    const onAssign = vi.fn();
    renderChecklist(scheduled(), onAssign);
    fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'ada' } });
    expect(onAssign).toHaveBeenCalledWith(VISUALS, 'ada');
  });

  it('lets a line be handed back to nobody', () => {
    const onAssign = vi.fn();
    renderChecklist(scheduled({ [VISUALS]: { assignee: 'bob' } }), onAssign);
    fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: '' } });
    expect(onAssign).toHaveBeenCalledWith(VISUALS, '');
  });

  it('keeps offering a name already on the record that is no longer in the list', () => {
    // A volunteer who has left the board still owns the line until somebody
    // says otherwise. Dropping them from the options would reassign the work
    // to nobody without anyone choosing that.
    renderChecklist(scheduled({ [VISUALS]: { assignee: 'erin' } }));
    expect((screen.getAllByRole('combobox')[0] as HTMLSelectElement).value).toBe('erin');
  });

  it('gives a promotion channel the same name on both screens', () => {
    // The record page and the inbox walk the same journey and used to name
    // the same line differently: `Forum announcement` here, always
    // tickable, and `Forum announcement (T-14)` in the inbox, withheld
    // until its window opened. The window was derived in the inbox alone.
    // It is `phaseItems` that lends a channel the window of the line it is
    // spliced after, so both screens read the one answer.
    const cfg = config({ channels: [{ key: 'forum', label: 'Forum announcement' }] });
    const s = speaker({
      status: 'scheduled',
      date: '2026-09-01',
      time: '12:30',
      edition_code: 'MRG-1',
      host_1: 'ada',
    });
    render(
      <Checklist
        speaker={s}
        onToggle={() => {}}
        onField={() => {}}
        config={cfg}
        today="2026-08-20"
      />,
    );
    const inboxLabel = deriveInbox([s], cfg, 'ada', 'organizer', '2026-08-20')
      .map(r => r.label)
      .find(l => l.startsWith('Forum announcement'));
    expect(inboxLabel).toBe('Forum announcement (T-14)');
    expect(screen.getByText(inboxLabel!)).toBeTruthy();
  });

  it('shows no control for a name left under a channel the config no longer has', () => {
    // What `docs/engineering/schema.md` says about removing a channel: the
    // owner already written under `promotion/<key>` stays in the file, on a
    // line no screen shows -- so there is nothing here offering to clear it,
    // and the appendix says which route does. The page used to claim the
    // entry "can still be cleared", which is the shape of overclaim this
    // branch spent three findings removing.
    const cfg = config({ channels: [{ key: 'forum', label: 'Forum announcement' }] });
    render(
      <Checklist
        speaker={speaker({
          status: 'scheduled',
          date: '2026-09-01',
          checklist: { 'promotion/gone': { assignee: 'ada' } },
        })}
        onToggle={() => {}}
        onField={() => {}}
        onAssign={() => {}}
        people={['ada']}
        config={cfg}
        today="2026-08-20"
      />,
    );
    expect(document.body.textContent).not.toContain('promotion/gone');
  });

  it('is simply absent on a screen with no writer', () => {
    render(
      <Checklist speaker={scheduled()} onToggle={() => {}} onField={() => {}} today="2026-08-20" />,
    );
    expect(screen.queryByRole('combobox')).toBeNull();
  });
});
