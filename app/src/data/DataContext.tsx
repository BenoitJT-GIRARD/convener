import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { useAuth } from '../auth/AuthContext';
import { getFile, putFile } from '../github/contents';
import { parseSpeakers, serializeSpeakers, parseConfig, serializeConfig } from './yaml';
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
  saveSpeakers: (next: Speaker[], message: string) => Promise<void>;
  saveConfig: (next: Config, message: string) => Promise<void>;
}

const C = createContext<Ctx | null>(null);

const DEFAULT_CONFIG: Config = {
  season: 2026,
  vw_counter: 1,
  vote_threshold: 3,
  overlap_window_days: 7,
  board_members: [],
};

function autoSweep(speakers: Speaker[], today: string): { swept: Speaker[]; changed: boolean } {
  let changed = false;
  const swept = speakers.map(s => {
    if (s.status === 'scheduled' && s.date && s.date < today) {
      changed = true;
      return { ...s, status: 'delivered' as const };
    }
    if (s.status === 'wrapped' && s.date) {
      const archiveAt = Date.parse(s.date) + 30 * 86400000;
      if (archiveAt < Date.parse(today)) {
        changed = true;
        return { ...s, status: 'archived' as const };
      }
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
      const today = new Date().toISOString().slice(0, 10);
      const parsed = parseSpeakers(spk.text);
      const { swept, changed } = autoSweep(parsed, today);
      const config = parseConfig(cfg.text) ?? DEFAULT_CONFIG;
      setS({
        loading: false,
        error: null,
        speakers: swept,
        config,
        spkSha: spk.sha,
        cfgSha: cfg.sha,
      });
      if (changed) {
        const text =
          '# Speakers (unified schema — see docs/reference/schema.md)\n' +
          serializeSpeakers(swept);
        const res: any = await putFile(
          'data/speakers.yml',
          text,
          spk.sha,
          'data: auto-sweep status by date',
          token,
        );
        setS(p => ({ ...p, spkSha: res.content.sha }));
      }
    } catch (e: any) {
      setS(p => ({ ...p, loading: false, error: e.message }));
    }
  }

  async function saveSpeakers(next: Speaker[], message: string) {
    if (!token) return;
    if (isDemoMode()) {
      setS(p => ({ ...p, speakers: next }));
      return;
    }
    const text =
      '# Speakers (unified schema — see docs/reference/schema.md)\n' +
      serializeSpeakers(next);
    const res: any = await putFile('data/speakers.yml', text, s.spkSha, message, token);
    setS(p => ({ ...p, speakers: next, spkSha: res.content.sha }));
  }

  async function saveConfig(next: Config, message: string) {
    if (!token || !s.cfgSha) return;
    if (isDemoMode()) {
      setS(p => ({ ...p, config: next }));
      return;
    }
    const text = '# Repo-wide config for the Convener app\n' + serializeConfig(next);
    const res: any = await putFile('data/config.yml', text, s.cfgSha, message, token);
    setS(p => ({ ...p, config: next, cfgSha: res.content.sha }));
  }

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return (
    <C.Provider value={{ ...s, reload, saveSpeakers, saveConfig }}>{children}</C.Provider>
  );
}

export function useData() {
  const c = useContext(C);
  if (!c) throw new Error('useData outside provider');
  return c;
}
