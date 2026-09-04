import { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { isDemoMode } from '../data/demo';
import { GitHubError } from '../github/client';
import { getFile } from '../github/contents';
import { eventIdOf } from '../state/agenda';
import { registrationsFile } from '../paths';
import type { Speaker } from '../data/types';

/**
 * The one wrap-up number this repository can work out for itself.
 *
 * Two numbers are asked for after a talk and both were typed in by hand from
 * somewhere else. They are not alike:
 *
 * - **How many registered** is already here.
 *   `instance/data/events/<event id>/registrations.enc` holds one envelope per
 *   person, and *how many envelopes there are* is ordinary JSON structure --
 *   readable without the private key, and disclosing nothing about anybody.
 *   Counting them is exactly the number the field asks for, and asking a
 *   volunteer to count a list the repository is already holding is asking
 *   them to be a slower reader of their own file.
 * - **The peak number in the room** is not here, and no amount of work would
 *   put it here: nothing in this repository records how many people were
 *   present at the same moment. The attendance export says who attended, not
 *   how many overlapped. That number is read off the meeting platform's own
 *   live view, by a person, on the day. So it stays a field, and its label
 *   says what it is rather than pretending the app could fill it.
 *
 * **Nothing is written until the volunteer clicks.** The count is offered,
 * not applied: a fetch on every render would put a network call behind a page
 * that is otherwise a read of two files, and a number written without anybody
 * asking is a number nobody checked. The click reads the file, and the field
 * above is filled with what it found.
 *
 * **Absent is a normal answer.** No registration file means the sign-up form
 * is not connected on this instance, or nobody used it -- D-13's ordinary
 * degradation, not a fault. The sentence says where the number comes from
 * instead, and the field stays exactly as it was.
 *
 * Not drawn in the demonstration, for the reason `InlineContent` does not
 * draw its own "edit" link there: the demonstration reads no repository of
 * its own, so a control that reaches for one would only ever report a
 * failure.
 */
export function RegistrationCount({
  speaker,
  onCounted,
}: {
  speaker: Speaker;
  onCounted: (count: number) => void;
}) {
  const { token } = useAuth();
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState('');

  if (isDemoMode() || !token || !speaker.edition_code) return null;

  async function count() {
    setBusy(true);
    setSaid('');
    try {
      const path = registrationsFile(eventIdOf(speaker.edition_code));
      const { text } = await getFile(path, token!);
      const parsed: unknown = JSON.parse(text);
      const entries =
        parsed && typeof parsed === 'object'
          ? (parsed as { registrations?: unknown }).registrations
          : undefined;
      if (!Array.isArray(entries)) {
        setSaid(
          `${path} is not a registration file this app can read. Nothing has been ` +
            'changed; type the number in above.',
        );
        return;
      }
      onCounted(entries.length);
    } catch (e) {
      // A 404 is the ordinary answer on an instance whose sign-up form is not
      // connected, so it is not reported as a failure. Anything else is.
      setSaid(
        e instanceof GitHubError && e.status === 404
          ? 'No sign-ups are recorded here for this edition. The number comes from ' +
              'wherever people signed up instead — type it in above.'
          : 'The sign-up file could not be read just now. Nothing has been changed.',
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="px-2 pt-1 pb-2 space-y-1">
      <button
        type="button"
        disabled={busy}
        onClick={count}
        className="font-display font-bold text-[11px] tracking-widest uppercase text-field-text border border-border px-2.5 py-1 hover:bg-paper-soft disabled:opacity-50"
      >
        {busy ? 'Counting…' : 'Count the sign-ups for me'}
      </button>
      {said && <p className="text-xs text-ink-muted">{said}</p>}
    </div>
  );
}
