import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { validateToken } from './api';

interface AuthState { token: string | null; login: string | null; ready: boolean; }
interface AuthCtx extends AuthState { signIn: (t: string) => Promise<boolean>; signOut: () => void; }
const Ctx = createContext<AuthCtx | null>(null);

const KEY = 'convener.token';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [s, setS] = useState<AuthState>({ token: null, login: null, ready: false });

  useEffect(() => {
    const stored = localStorage.getItem(KEY);
    if (!stored) { setS({ token: null, login: null, ready: true }); return; }
    validateToken(stored).then(u =>
      setS({ token: u ? stored : null, login: u?.login ?? null, ready: true })
    );
  }, []);

  async function signIn(t: string) {
    const u = await validateToken(t);
    if (!u) return false;
    localStorage.setItem(KEY, t);
    setS({ token: t, login: u.login, ready: true });
    return true;
  }
  function signOut() {
    localStorage.removeItem(KEY);
    setS({ token: null, login: null, ready: true });
  }
  return <Ctx.Provider value={{ ...s, signIn, signOut }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error('useAuth outside provider');
  return c;
}
