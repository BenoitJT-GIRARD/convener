import { useEffect } from 'react';
import { useData } from '../data/DataContext';

/**
 * What this tab has changed and not written yet, and the three ways it gets
 * written.
 *
 * **Why anything is held at all.** Every write to `instance/data/speakers.yml`
 * is a commit, and every commit is a push that wakes the repository's
 * workflows. Ticking a box made one; typing into a checklist field made one
 * *per keystroke*, because those inputs fire on `change`. On the instance this
 * product was derived for, one operator's runbook session made 53 commits in
 * 47 minutes and spent 1175 billed Actions minutes — more than half a GitHub
 * Free month (`docs/operating/what-the-automation-costs.md`).
 *
 * **Why it is visible.** Held work that nobody can see is work a volunteer
 * does not know they can lose. This says how much is waiting, at all times,
 * and offers the button that ends the wait — so the batching is never
 * something the screen does behind them.
 *
 * **The ways it is written.** The control here; `mutateSpeakers`, at the one
 * chokepoint every other write passes through — so a transition empties the
 * queue before it changes a status, without any of its callers having to
 * remember; and two edges the provider cannot see, both of them here: the
 * volunteer leaving the record, and the page being hidden. Last of all a
 * timer in `DataContext`, twenty minutes after the last edit.
 *
 * The timer is the backstop, not the mechanism. In ordinary use a
 * volunteer's work is written when they move on or switch away, and the
 * timer only ever catches a record left open on a screen nobody is at. That
 * is what lets it be as long as it is — a net that caught the ordinary case
 * would be splitting somebody's work into commits at the rhythm of their
 * pauses.
 */
export function PendingEdits() {
  const { pendingEdits, flushSpeakers } = useData();

  // Leaving the record writes what is held. The cleanup runs on unmount --
  // a different speaker, another screen, a sign-out -- which is the moment a
  // queue would otherwise sit there belonging to a record nobody is looking
  // at any more.
  useEffect(() => {
    return () => {
      void flushSpeakers();
    };
    // Once, for the life of this record's screen. Re-running it on every
    // change of `flushSpeakers` would flush on each render instead.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Switching away writes what is held.
  //
  // This is what makes a twenty-minute timer safe. A backgrounded tab can be
  // discarded by the browser for memory, and a laptop can sleep, and neither
  // runs an unload handler anybody should rely on -- so at that length, held
  // work behind a hidden tab is work genuinely at risk. `visibilitychange`
  // fires while the page is still alive, which `beforeunload` cannot promise.
  //
  // It is also the right moment rather than merely a safe one: a volunteer
  // switches away to go and do the thing the line describes. Writing here
  // gives one commit per stretch of work on a record instead of one per
  // pause in it, which is the same granularity the timer is trying to reach
  // and arrives at it by watching the volunteer rather than the clock.
  useEffect(() => {
    function onHidden() {
      if (document.visibilityState === 'hidden') void flushSpeakers();
    }
    document.addEventListener('visibilitychange', onHidden);
    return () => document.removeEventListener('visibilitychange', onHidden);
  }, [flushSpeakers]);

  // Closing the tab is the one edge nothing can be written on: a browser will
  // not wait for an asynchronous write during unload, and pretending
  // otherwise would be worse than saying so. This asks the browser to warn,
  // which is all that is honestly available -- and after the effect above it
  // is a second net rather than the only one.
  useEffect(() => {
    if (pendingEdits === 0) return;
    function warn(e: BeforeUnloadEvent) {
      e.preventDefault();
    }
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [pendingEdits]);

  if (pendingEdits === 0) return null;

  return (
    <div
      className="flex items-center gap-3 text-xs border border-border rounded px-3 py-2 bg-surface-mute"
      // Announced rather than merely drawn: the count changes without the
      // volunteer doing anything to this element, and a screen reader would
      // otherwise never mention that anything is outstanding.
      role="status"
      aria-live="polite"
    >
      <span className="text-ink-muted">
        {pendingEdits === 1 ? '1 change not saved yet' : `${pendingEdits} changes not saved yet`} —
        saving shortly.
      </span>
      <button
        type="button"
        onClick={() => void flushSpeakers()}
        className="font-display font-bold uppercase tracking-widest text-dominant underline"
      >
        Save now
      </button>
    </div>
  );
}
