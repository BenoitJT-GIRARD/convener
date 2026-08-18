import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { useAuth } from '../auth/AuthContext';
import { getFile, githubStore } from '../github/contents';
import { mutate } from '../github/mutate';
import {
  parseSpeakers,
  serializeSpeakers,
  parseConfig,
  serializeConfig,
  withSpeakersHeader,
  withConfigHeader,
} from './yaml';
import { isDemoMode, DEMO_SPEAKERS, DEMO_CONFIG } from './demo';
import type { Speaker, Config } from './types';

interface State {
  loading: boolean;
  error: string | null;
  speakers: Speaker[];
  config: Config | null;
  spkSha: string;
  cfgSha: string;
}

interface Ctx extends State {
  reload: () => Promise<void>;
  mutateSpeakers: (transform: (current: Speaker[]) => Speaker[], message: string) => Promise<void>;
  mutateConfig: (transform: (current: Config) => Config, message: string) => Promise<void>;
}

const C = createContext<Ctx | null>(null);

const DEFAULT_CONFIG: Config = {
  season: 2026,
  vw_counter: 1,
  vote_threshold: 3,
  overlap_window_days: 7,
  seminar_duration_minutes: 90,
  board_members: [],
};

/**
 * Convert a wall-time in Europe/Paris (DST-aware) to a UTC epoch.
 * dateStr: YYYY-MM-DD; timeStr: HH:MM.
 */
function parisWallTimeToEpoch(dateStr: string, timeStr: string): number {
  const iso = `${dateStr}T${timeStr}:00`;
  const probe = new Date(`${iso}Z`);
  const fmt = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Europe/Paris',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
  const parts = fmt.formatToParts(probe);
  const map: Record<string, string> = {};
  for (const p of parts) if (p.type !== 'literal') map[p.type] = p.value;
  const hour = map.hour === '24' ? '00' : map.hour;
  const parisIso = `${map.year}-${map.month}-${map.day}T${hour}:${map.minute}:${map.second}Z`;
  const offsetMs = Date.parse(parisIso) - probe.getTime();
  return probe.getTime() - offsetMs;
}

function autoSweep(
  speakers: Speaker[],
  config: Config | null,
  now: Date,
): { swept: Speaker[]; changed: boolean } {
  const duration = (config?.seminar_duration_minutes ?? 90) * 60_000;
  let changed = false;
  const swept = speakers.map(s => {
    if (s.status !== 'scheduled' || !s.date) return s;
    if (s.time) {
      const startEpoch = parisWallTimeToEpoch(s.date, s.time);
      if (now.getTime() >= startEpoch + duration) {
        changed = true;
        return { ...s, status: 'delivered' as const };
      }
      return s;
    }
    // Legacy fallback: no time — flip the day after.
    const todayStr = now.toISOString().slice(0, 10);
    if (s.date < todayStr) {
      changed = true;
      return { ...s, status: 'delivered' as const };
    }
    return s;
  });
  return { swept, changed };
}

export function DataProvider({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  const [s, setS] = useState<State>({
    loading: true,
    error: null,
    speakers: [],
    config: null,
    spkSha: '',
    cfgSha: '',
  });

  async function reload() {
    if (!token) return;
    if (isDemoMode()) {
      setS({
        loading: false,
        error: null,
        speakers: [...DEMO_SPEAKERS],
        config: { ...DEMO_CONFIG },
        spkSha: 'demo',
        cfgSha: 'demo',
      });
      return;
    }
    setS(p => ({ ...p, loading: true, error: null }));
    try {
      const [spk, cfg] = await Promise.all([
        getFile('data/speakers.yml', token),
        getFile('data/config.yml', token),
      ]);
      const parsed = parseSpeakers(spk.text);
      const config = parseConfig(cfg.text) ?? DEFAULT_CONFIG;
      const { swept, changed } = autoSweep(parsed, config, new Date());
      setS({
        loading: false,
        error: null,
        speakers: swept,
        config,
        spkSha: spk.sha,
        cfgSha: cfg.sha,
      });
      if (changed) {
        const result = await mutate({
          store: githubStore(token),
          path: 'data/speakers.yml',
          parse: parseSpeakers,
          serialize: v => withSpeakersHeader(serializeSpeakers(v)),
          transform: current => autoSweep(current, config, new Date()).swept,
          message: 'data: auto-sweep scheduled→delivered',
        });
        setS(p => ({ ...p, speakers: result.value, spkSha: result.sha }));
      }
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setS(p => ({ ...p, loading: false, error: message }));
    }
  }

  async function mutateSpeakers(
    transform: (current: Speaker[]) => Speaker[],
    message: string,
  ) {
    if (!token) return;
    if (isDemoMode()) {
      setS(p => ({ ...p, speakers: transform(p.speakers) }));
      return;
    }
    const result = await mutate({
      store: githubStore(token),
      path: 'data/speakers.yml',
      parse: parseSpeakers,
      serialize: v => withSpeakersHeader(serializeSpeakers(v)),
      transform,
      message,
    });
    setS(p => ({ ...p, speakers: result.value, spkSha: result.sha }));
  }

  async function mutateConfig(
    transform: (current: Config) => Config,
    message: string,
  ) {
    if (!token) return;
    if (isDemoMode()) {
      setS(p => ({ ...p, config: p.config ? transform(p.config) : p.config }));
      return;
    }
    const result = await mutate({
      store: githubStore(token),
      path: 'data/config.yml',
      parse: text => parseConfig(text) ?? DEFAULT_CONFIG,
      serialize: v => withConfigHeader(serializeConfig(v)),
      transform,
      message,
    });
    setS(p => ({ ...p, config: result.value, cfgSha: result.sha }));
  }

  useEffect(() => {
    // `reload` sets state synchronously before its first `await` (the demo-mode
    // branch, and the initial `loading: true` flag). Deferring those updates
    // would require reworking the whole load/save state machine in this file,
    // which Task 12 does as a dedicated rewrite — narrowly disabling here avoids
    // a throwaway restructuring that would just be redone.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    reload();
    // `reload` is redefined every render (it closes over `s`); adding it here
    // would re-run the effect on every render and loop. Task 12 rewrites this
    // block (state machine refactor) and will fix the dependency properly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return (
    <C.Provider value={{ ...s, reload, mutateSpeakers, mutateConfig }}>{children}</C.Provider>
  );
}

export function useData() {
  const c = useContext(C);
  if (!c) throw new Error('useData outside provider');
  return c;
}
