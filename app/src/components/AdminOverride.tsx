import { useState } from 'react';
import { useData } from '../data/DataContext';
import { useAuth } from '../auth/AuthContext';
import type { Speaker, SpeakerStatus } from '../data/types';

const ALL_STATUSES: SpeakerStatus[] = [
  'lead',
  'approved',
  'invited',
  'confirmed',
  'scheduled',
  'delivered',
  'wrapped',
  'archived',
  'parked',
  'decline-board',
  'decline-speaker',
];

export function AdminOverride({ speaker }: { speaker: Speaker }) {
  const { speakers, saveSpeakers } = useData();
  const { login } = useAuth();
  const [target, setTarget] = useState<SpeakerStatus>(speaker.status);
  const [busy, setBusy] = useState(false);

  async function apply() {
    if (!login || target === speaker.status) return;
    setBusy(true);
    try {
      const updated = speakers.map(sp =>
        sp.id === speaker.id ? { ...sp, status: target } : sp,
      );
      await saveSpeakers(
        updated,
        `data: ${speaker.id} admin override ${speaker.status}→${target} by ${login}`,
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 flex gap-2 items-center flex-wrap">
      <select
        value={target}
        onChange={e => setTarget(e.target.value as SpeakerStatus)}
        className="px-2 py-1 border border-border rounded text-sm"
      >
        {ALL_STATUSES.map(st => (
          <option key={st} value={st}>
            {st}
          </option>
        ))}
      </select>
      <button
        disabled={busy || target === speaker.status}
        onClick={apply}
        className="px-3 py-1.5 text-sm rounded border border-danger text-danger hover:bg-danger hover:text-white disabled:opacity-50"
      >
        Force status
      </button>
      <span className="text-xs text-ink-muted">Logged in commit message.</span>
    </div>
  );
}
