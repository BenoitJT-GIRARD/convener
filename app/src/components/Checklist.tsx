import { useState } from 'react';
import type { Config, Speaker } from '../data/types';
import {
  canCarryOwner,
  isItemDone,
  phaseOf,
  phaseItems,
  fieldValue,
  stepBefore,
  type RunbookItem,
  type FieldKey,
} from '../state/phases';
import { itemAssignee } from '../state/assignment';
import { parisToday } from '../state/derived';
import { InlineContent } from '../content/InlineContent';

interface Props {
  speaker: Speaker;
  onToggle: (key: string, value: boolean) => void;
  onField: (field: FieldKey, value: string) => void;
  /** Records who owes one line. Absent -- on a screen with no writer, or
   *  before anyone is signed in -- simply hides the control; the journey
   *  reads exactly as it did before. */
  onAssign?: (key: string, login: string) => void;
  /** The people who can be put down for a line, as logins. A closed list
   *  rather than a text box: an owner this app cannot recognise is one the
   *  inbox would never match, so a typo would silently file the work with
   *  nobody. */
  people?: string[];
  /** The loaded configuration, for the lines of the journey that live in it:
   *  the places an event is announced. Absent -- nothing loaded -- shows the
   *  static journey, which is what the screen showed before those lines
   *  existed. */
  config?: Config | null;
  /**
   * What fills the `button-group` lines, keyed by their journey key.
   *
   * The date negotiation and the buttons that close a status are not
   * checklist rows and never will be, but *where they sit* is a fact about
   * the journey and belongs in `state/phases.ts` with the rest of it. They
   * used to sit above the whole checklist, in a block of their own, which is
   * how a volunteer came to be asked to mark an invitation sent before the
   * app would let them choose the dates it names.
   *
   * A key with nothing against it renders nothing, so a screen with no
   * writer -- the demonstration's read-only views, a test of the rows alone
   * -- shows the journey exactly as it did before these lines existed.
   */
  slots?: Record<string, React.ReactNode>;
  disabled?: boolean;
  today?: string;
}

export function Checklist({
  speaker,
  onToggle,
  onField,
  onAssign,
  people,
  config,
  slots,
  disabled,
  today,
}: Props) {
  const phase = phaseOf(speaker.status);
  if (!phase) return null;
  const todayStr = today ?? parisToday();
  const targetDate = speaker.date ? Date.parse(speaker.date) : null;
  const daysUntil =
    targetDate !== null
      ? Math.round((targetDate - Date.parse(todayStr)) / 86400000)
      : null;

  const items = phaseItems(phase, config ?? null);
  return (
    <div className="space-y-3">
      <h2 className="font-serif text-xl mb-3">{phase.label}</h2>
      {items.some(item => outstanding(speaker, item)) && <StarNote />}
      {items.map(item =>
        item.form === 'button-group' ? (
          <div key={item.key}>{slots?.[item.key] ?? null}</div>
        ) : (
          <div key={item.key}>
            <Row
              item={item}
              speaker={speaker}
              inWindow={item.window === undefined || daysUntil === null || daysUntil <= item.window}
              disabled={disabled}
              onToggle={onToggle}
              onField={onField}
            />
            {onAssign && canCarryOwner(item) && (
              <Owner
                item={item}
                speaker={speaker}
                people={people ?? []}
                disabled={disabled}
                onAssign={onAssign}
              />
            )}
          </div>
        ),
      )}
    </div>
  );
}

interface RowProps {
  item: RunbookItem;
  speaker: Speaker;
  inWindow: boolean;
  disabled?: boolean;
  onToggle: (key: string, value: boolean) => void;
  onField: (field: FieldKey, value: string) => void;
}

function Row({ item, speaker, inWindow, disabled, onToggle, onField }: RowProps) {
  switch (item.form) {
    case 'content':
      return <ContentRow item={item} speaker={speaker} />;
    case 'field':
      return <FieldRow item={item} speaker={speaker} disabled={disabled} onField={onField} />;
    case 'checkbox':
      return (
        <CheckboxRow
          item={item}
          speaker={speaker}
          inWindow={inWindow}
          disabled={disabled}
          onToggle={onToggle}
        />
      );
    // Filled by the record page through `slots` and never reached here:
    // `Checklist` renders these lines itself, above.
    case 'button-group':
      return null;
  }
}

/**
 * Who does this line.
 *
 * Drawn only against a task (`phases.ts::canCarryOwner`), which is the whole
 * of what the control is for: a page to read and a field that already names
 * its own owner used to carry one too, and a control offered where it means
 * nothing is a control people learn to skip everywhere.
 *
 * Nobody is the default and reads as the arrangement it is -- "the hosts,
 * unless someone else takes it" -- in the same muted type as every other
 * label on the row. It replaced "Nobody in particular (hosts)", which stated
 * the same arrangement in a shape a reader had to decode. There is no warning
 * colour, no asterisk and no count of unclaimed lines anywhere: not naming
 * somebody is what the series has always done, and a tool that scolds
 * volunteers over a field they never asked for is a tool they stop using.
 *
 * The wording is about the work and the arrangement, never about a person's
 * standing. `state/sla.ts` keeps the same discipline for lateness, and there
 * is no sentence here a name could turn into a judgement.
 */
function Owner({
  item,
  speaker,
  people,
  disabled,
  onAssign,
}: {
  item: RunbookItem;
  speaker: Speaker;
  people: string[];
  disabled?: boolean;
  onAssign: (key: string, login: string) => void;
}) {
  const current = itemAssignee(speaker, item.key);
  // A name already on the record that is no longer among the people offered --
  // a volunteer who has left the board, say -- stays selectable, because
  // dropping it from the list would silently reassign the line to nobody.
  const options = people.includes(current) || current === '' ? people : [current, ...people];
  return (
    <label className="flex items-baseline gap-2 px-2 pt-1 pb-2 text-xs text-ink-muted">
      <span className="font-display font-bold uppercase tracking-widest">Who does this</span>
      <select
        value={current}
        disabled={disabled}
        onChange={e => onAssign(item.key, e.target.value)}
        className="text-xs bg-transparent border-b border-border"
      >
        <option value="">the hosts, unless someone else takes it</option>
        {options.map(login => (
          <option key={login} value={login}>
            {login}
          </option>
        ))}
      </select>
    </label>
  );
}

function ContentRow({ item, speaker }: { item: RunbookItem; speaker: Speaker }) {
  if (!item.contentKey) return null;
  const today = parisToday();
  return (
    <details className="border border-border rounded p-3 open:bg-surface-mute" open>
      <summary className="cursor-pointer font-display font-bold text-xs uppercase tracking-widest text-dominant">
        {item.label}
      </summary>
      <div className="mt-3">
        <InlineContent
          contentKey={item.contentKey}
          ctx={{ speaker, host: speaker.host_1, today }}
        />
      </div>
    </details>
  );
}

function FieldRow({
  item,
  speaker,
  disabled,
  onField,
}: {
  item: RunbookItem;
  speaker: Speaker;
  disabled?: boolean;
  onField: (field: FieldKey, value: string) => void;
}) {
  const k = item.fieldKey!;
  const raw = fieldValue(speaker, k);
  const value = raw === null || raw === undefined ? '' : String(raw);
  const long = k === 'abstract';
  const num =
    k === 'registrations' ||
    k === 'live_peak' ||
    k === 'youtube_views_30d' ||
    k === 'forum_replies';
  return (
    <label className="block border border-border rounded p-3">
      <span className="font-display font-bold text-xs uppercase tracking-widest text-ink-muted">
        {item.label}
        {outstanding(speaker, item) && <span className="text-danger ml-1">*</span>}
      </span>
      {long ? (
        <textarea
          value={value}
          onChange={e => onField(k, e.target.value)}
          disabled={disabled}
          rows={4}
          className="w-full mt-2 px-2 py-2 text-sm font-sans"
        />
      ) : (
        <input
          type={num ? 'number' : 'text'}
          value={value}
          onChange={e => onField(k, e.target.value)}
          disabled={disabled}
          className="w-full mt-2 px-2 py-1.5 text-sm"
        />
      )}
    </label>
  );
}

/** The asterisk means "this one is not optional", and a line that stops the
 *  archive from three weeks before the talk is as far from optional as the
 *  journey gets. Reading only `required` would have left the one line the
 *  volunteers write in capitals looking like every other tick. */
function mustBeDone(item: RunbookItem): boolean {
  return item.required === true || item.blocksFinalisation === true;
}

/**
 * A line that is not optional and is not done yet -- which is what the red
 * star marks.
 *
 * It used to mark every line that was not optional, done or not, and said so
 * nowhere. That is two defects in one mark: a page of stars a volunteer has
 * already satisfied teaches them the star means nothing, and a star with no
 * note beside it anywhere on the screen is a symbol without a key -- the
 * orphan beside *Registrations* that R42 records. Marking only what is
 * outstanding makes the page empty itself as the work is done, and gives the
 * one sentence below something true to say.
 */
function outstanding(speaker: Speaker, item: RunbookItem): boolean {
  return mustBeDone(item) && !isItemDone(speaker, item);
}

/** The star's own note, drawn once, and only while at least one star is on
 *  the page. */
function StarNote() {
  return (
    <p className="text-xs text-ink-muted">
      <span className="text-danger">*</span> marks what this record still needs
      before it can move on.
    </p>
  );
}

function CheckboxRow({
  item,
  speaker,
  inWindow,
  disabled,
  onToggle,
}: {
  item: RunbookItem;
  speaker: Speaker;
  inWindow: boolean;
  disabled?: boolean;
  onToggle: (key: string, value: boolean) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  // Released by the volunteer, for this row, for as long as the screen is
  // open. Nothing about it is written down: what the record keeps is which
  // steps happened, and "the order was odd" is not a fact about the event.
  const [released, setReleased] = useState(false);
  const checked = !!speaker.runbook_progress[item.key];
  const previous = stepBefore(speaker, item);
  const held = previous !== undefined && !released;
  const label = item.window !== undefined ? `${item.label} (T-${item.window})` : item.label;
  const today = parisToday();
  return (
    <div className={`border border-border rounded p-2 ${inWindow ? '' : 'bg-paper-soft'}`}>
      <div className="flex items-start gap-2">
        <input
          type="checkbox"
          checked={checked}
          disabled={disabled || held}
          onChange={e => onToggle(item.key, e.target.checked)}
          className="mt-1 accent-field"
        />
        <div className="flex-1">
          <p className="text-sm">
            {label}
            {outstanding(speaker, item) && <span className="text-danger ml-1">*</span>}
          </p>
          {item.note && <p className="text-xs text-ink-muted mt-1">{item.note}</p>}
          {previous !== undefined && (
            <div className="mt-1">
              <p className="text-xs text-ink-muted">Comes after “{previous.label}”.</p>
              {held && (
                <button
                  type="button"
                  onClick={() => setReleased(true)}
                  className="text-xs text-field-text underline mt-1"
                >
                  It happened in another order — tick it anyway
                </button>
              )}
            </div>
          )}
          {item.contentKey && (
            <button
              type="button"
              onClick={() => setExpanded(!expanded)}
              className="text-xs text-field-text underline mt-1"
            >
              {expanded ? 'Hide' : 'Show'} content
            </button>
          )}
        </div>
      </div>
      {expanded && item.contentKey && (
        <div className="mt-2">
          <InlineContent
            contentKey={item.contentKey}
            ctx={{ speaker, host: speaker.host_1, today }}
          />
        </div>
      )}
    </div>
  );
}
