import { useState } from 'react';
import type { Speaker } from '../data/types';
import { phaseOf, fieldValue, type RunbookItem, type FieldKey } from '../state/phases';
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
  disabled?: boolean;
  today?: string;
}

export function Checklist({ speaker, onToggle, onField, onAssign, people, disabled, today }: Props) {
  const phase = phaseOf(speaker.status);
  if (!phase) return null;
  const todayStr = today ?? parisToday();
  const targetDate = speaker.date ? Date.parse(speaker.date) : null;
  const daysUntil =
    targetDate !== null
      ? Math.round((targetDate - Date.parse(todayStr)) / 86400000)
      : null;

  return (
    <div className="space-y-3">
      <h2 className="font-serif text-xl mb-3">{phase.label}</h2>
      {phase.items.map(item => (
        <div key={item.key}>
          <Row
            item={item}
            speaker={speaker}
            inWindow={item.window === undefined || daysUntil === null || daysUntil <= item.window}
            disabled={disabled}
            onToggle={onToggle}
            onField={onField}
          />
          {onAssign && (
            <Owner
              item={item}
              speaker={speaker}
              people={people ?? []}
              disabled={disabled}
              onAssign={onAssign}
            />
          )}
        </div>
      ))}
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
    case 'button-group':
      return null;
  }
}

/**
 * Who owes this line.
 *
 * Nobody is the default and reads as a plain statement of fact -- "Nobody in
 * particular (hosts)" -- in the same muted type as every other label on the
 * row. There is no warning colour, no asterisk and no count of unassigned
 * lines anywhere: not naming an owner is what the series has always done, and
 * a tool that scolds volunteers over a field they never asked for is a tool
 * they stop using.
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
      <span className="font-display font-bold uppercase tracking-widest">Owner</span>
      <select
        value={current}
        disabled={disabled}
        onChange={e => onAssign(item.key, e.target.value)}
        className="text-xs bg-transparent border-b border-border"
      >
        <option value="">Nobody in particular (hosts)</option>
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
      <summary className="cursor-pointer font-display font-bold text-xs uppercase tracking-widest text-accent">
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
        {item.required && <span className="text-danger ml-1">*</span>}
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
  const checked = !!speaker.runbook_progress[item.key];
  const label = item.window !== undefined ? `${item.label} (T-${item.window})` : item.label;
  const today = parisToday();
  return (
    <div className={`border border-border rounded p-2 ${inWindow ? '' : 'opacity-50'}`}>
      <div className="flex items-start gap-2">
        <input
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={e => onToggle(item.key, e.target.checked)}
          className="mt-1 accent-primary"
        />
        <div className="flex-1">
          <p className="text-sm">
            {label}
            {item.required && <span className="text-danger ml-1">*</span>}
          </p>
          {item.contentKey && (
            <button
              type="button"
              onClick={() => setExpanded(!expanded)}
              className="text-xs text-primary-hover underline mt-1"
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
