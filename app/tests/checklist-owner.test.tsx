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
import { Checklist } from '../src/components/Checklist';
import { speaker } from './data-doubles';

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
  it('reads as nobody in particular until somebody is named', () => {
    renderChecklist();
    const owners = screen.getAllByRole('combobox');
    expect(owners.length).toBeGreaterThan(0);
    for (const owner of owners) {
      expect((owner as HTMLSelectElement).value).toBe('');
    }
    expect(screen.getAllByText('Nobody in particular (hosts)').length).toBe(owners.length);
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

  it('is simply absent on a screen with no writer', () => {
    render(
      <Checklist speaker={scheduled()} onToggle={() => {}} onField={() => {}} today="2026-08-20" />,
    );
    expect(screen.queryByRole('combobox')).toBeNull();
  });
});
