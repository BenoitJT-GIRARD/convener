import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { useAuth } from '../auth/AuthContext';
import { getFile, putFile } from '../github/contents';
import { parseSpeakers, parseEvents, serializeSpeakers, serializeEvents } from './yaml';
import type { Speaker, VwsEvent } from './types';

interface State {
  loading: boolean;
  error: string | null;
  speakers: Speaker[];
  events: VwsEvent[];
  spkSha: string;
  evSha: string;
}

interface Ctx extends State {
  reload: () => Promise<void>;
  saveSpeakers: (next: Speaker[], message: string) => Promise<void>;
  saveEvents: (next: VwsEvent[], message: string) => Promise<void>;
}

const C = createContext<Ctx | null>(null);

export function DataProvider({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  const [s, setS] = useState<State>({
    loading: true, error: null, speakers: [], events: [], spkSha: '', evSha: '',
  });

  async function reload() {
    if (!token) return;
    setS(p => ({ ...p, loading: true, error: null }));
    try {
      const [spk, ev] = await Promise.all([
        getFile('data/speakers.yml', token),
        getFile('data/events.yml', token),
      ]);
      setS({
        loading: false, error: null,
        speakers: parseSpeakers(spk.text), events: parseEvents(ev.text),
        spkSha: spk.sha, evSha: ev.sha,
      });
    } catch (e: any) {
      setS(p => ({ ...p, loading: false, error: e.message }));
    }
  }

  async function saveSpeakers(next: Speaker[], message: string) {
    if (!token) return;
    const yaml = '# Speaker pipeline (Track 1) — see schema.md\n' + serializeSpeakers(next);
    const res: any = await putFile('data/speakers.yml', yaml, s.spkSha, message, token);
    setS(p => ({ ...p, speakers: next, spkSha: res.content.sha }));
  }

  async function saveEvents(next: VwsEvent[], message: string) {
    if (!token) return;
    const yaml = '# Event registry (Track 2) — see schema.md\n' + serializeEvents(next);
    const res: any = await putFile('data/events.yml', yaml, s.evSha, message, token);
    setS(p => ({ ...p, events: next, evSha: res.content.sha }));
  }

  useEffect(() => { reload(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [token]);

  return <C.Provider value={{ ...s, reload, saveSpeakers, saveEvents }}>{children}</C.Provider>;
}

export function useData() {
  const c = useContext(C);
  if (!c) throw new Error('useData outside provider');
  return c;
}
