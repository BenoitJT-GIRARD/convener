import type { Speaker } from '../data/types';
import { phaseOf, type RunbookItem } from '../state/phases';

interface Props {
  speaker: Speaker;
  onToggle: (key: string, value: boolean) => void;
  disabled?: boolean;
  today?: string;
}

export function Checklist({ speaker, onToggle, disabled, today }: Props) {
  const phase = phaseOf(speaker.status);
  if (!phase) return null;
  const todayStr = today ?? new Date().toISOString().slice(0, 10);
  const targetDate = speaker.date ? Date.parse(speaker.date) : null;
  const daysUntil =
    targetDate !== null
      ? Math.round((targetDate - Date.parse(todayStr)) / 86400000)
      : null;

  return (
    <div className="space-y-2">
      <h2 className="font-serif text-xl mb-3">{phase.label}</h2>
      {phase.items.map(item => (
        <RunbookRow
          key={item.key}
          item={item}
          checked={!!speaker.runbook_progress[item.key]}
          inWindow={item.window === undefined || daysUntil === null || daysUntil <= item.window}
          disabled={disabled}
          onToggle={onToggle}
        />
      ))}
      {phase.autoAdvance && (
        <p className="text-xs text-ink-muted mt-3">
          When all gates checked, status advances to <strong>{phase.autoAdvance}</strong>.
        </p>
      )}
    </div>
  );
}

interface RowProps {
  item: RunbookItem;
  checked: boolean;
  inWindow: boolean;
  disabled?: boolean;
  onToggle: (key: string, value: boolean) => void;
}

function RunbookRow({ item, checked, inWindow, disabled, onToggle }: RowProps) {
  const label = item.window !== undefined ? `${item.label} (T-${item.window})` : item.label;
  return (
    <label
      className={`flex items-start gap-2 p-2 rounded border border-transparent hover:border-border transition-colors ${
        inWindow ? '' : 'opacity-50'
      }`}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={e => onToggle(item.key, e.target.checked)}
        className="mt-1 accent-primary"
      />
      <span className={`text-sm ${item.gate ? 'font-medium' : ''}`}>
        {label}
        {item.gate && <span className="ml-1 text-xs text-primary">(gate)</span>}
      </span>
    </label>
  );
}
