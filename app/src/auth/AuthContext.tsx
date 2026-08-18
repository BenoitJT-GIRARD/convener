import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { validateToken } from './api';
import { isDemoMode, exitDemoMode, DEMO_USER } from '../data/demo';

interface AuthState { token: string | null; login: string | null; ready: boolean; }
interface AuthCtx extends AuthState { signIn: (t: string) => Promise<boolean>; signOut: () => void; }
const Ctx = createContext<AuthCtx | null>(null);

const KEY = 'convener.token';

/** Synchronous part of the initial auth state: demo mode and "no stored token"
 *  can be resolved immediately, so they're computed in the useState initialiser
 *  instead of being set from inside the effect below. */
function initialAuthState(): AuthState {
  if (isDemoMode()) return { token: 'demo', login: DEMO_USER.login, ready: true };
  const stored = localStorage.getItem(KEY);
  if (!stored) return { token: null, login: null, ready: true };
  return { token: stored, login: null, ready: false };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [s, setS] = useState<AuthState>(initialAuthState);

  useEffect(() => {
    if (isDemoMode()) return;
    const stored = localStorage.getItem(KEY);
    if (!stored) return;
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
    exitDemoMode();
    setS({ token: null, login: null, ready: true });
  }
  return <Ctx.Provider value={{ ...s, signIn, signOut }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error('useAuth outside provider');
  return c;
}
