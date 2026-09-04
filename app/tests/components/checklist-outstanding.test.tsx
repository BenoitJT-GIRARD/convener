/**
 * The red star, and the sentence that says what it means.
 *
 * Two defects in one mark, both recorded by the maintainer walking the
 * pipeline (R36, R42). The star sat beside every line that was not optional,
 * done or not -- so a page of stars a volunteer had already satisfied taught
 * them the mark meant nothing. And nothing on the screen said what it was:
 * the one beside *Registrations* was a symbol with no key anywhere on the
 * page. The star now marks only what is still outstanding, and it brings its
 * own note the moment it appears.
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AuthProvider } from '../../src/auth/AuthContext';
import { Checklist } from '../../src/components/Checklist';
import { speaker } from '../helpers/data-doubles';

const NOTE = /marks what this record still needs before it can move on/;

function show(s: Parameters<typeof speaker>[0]) {
  render(
    <AuthProvider>
      <Checklist speaker={speaker(s)} onToggle={() => {}} onField={() => {}} today="2026-08-20" />
    </AuthProvider>,
  );
}

/** The stars on the page, as the labels they sit beside. The note's own
 *  star is not one of them: it is the key, not a mark on a line. */
function starred(): string[] {
  return [...document.querySelectorAll('span.text-danger')]
    .filter(star => star.textContent === '*')
    .map(star => star.parentElement?.textContent?.replace('*', '').trim() ?? '')
    .filter(label => !NOTE.test(label));
}

describe('what a record still needs', () => {
  it('stars an empty wrap-up number, and says what the star means', () => {
    show({ status: 'delivered', date: '2026-08-01' });
    expect(starred()).toContain('Registrations');
    expect(screen.getByText(NOTE)).toBeTruthy();
  });

  it('takes the star off a line as soon as it is filled in', () => {
    show({
      status: 'delivered',
      date: '2026-08-01',
      metrics: { registrations: 40, live_peak: null, youtube_views_30d: null, forum_replies: null },
    });
    expect(starred()).not.toContain('Registrations');
    expect(starred()).toContain('Live peak');
  });

  it('takes the star off a tick as soon as it is ticked', () => {
    const done = { 'delivered/forum-summary': true };
    show({ status: 'delivered', date: '2026-08-01' });
    expect(starred()).toContain('Forum summary posted');
    document.body.innerHTML = '';
    show({ status: 'delivered', date: '2026-08-01', runbook_progress: done });
    expect(starred()).not.toContain('Forum summary posted');
  });

  it('draws no note at all on a phase with nothing outstanding', () => {
    // Both hosts named is the whole of what the approved phase asks for, so
    // a record that has them shows a page with no star and no key to one.
    show({ status: 'approved', host_1: 'ada', host_2: 'bob' });
    expect(starred()).toEqual([]);
    expect(screen.queryByText(NOTE)).toBeNull();
  });

  it('stars the talk details a date cannot be locked without', () => {
    // `dates.lockBlockers` names Title and Abstract, and this is where the
    // volunteer meets them. The third, the edition number, is typed into the
    // lock-in form and carries its star there.
    show({ status: 'confirmed', title: '', abstract: '' });
    expect(starred()).toEqual(['Title', 'Abstract']);
  });
});
