import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { validateToken } from './api';
import { isDemoMode, exitDemoMode, DEMO_USER } from '../data/demo';

interface AuthState {
  token: string | null;
  login: string | null;
  ready: boolean;
  /** Set when startup could not even determine sign-in state (for example a
   *  network failure while validating a stored token). Distinct from "ready,
   *  no token", which just means "please sign in". */
  startupError: string | null;
}
interface AuthCtx extends AuthState {
  signIn: (t: string) => Promise<boolean>;
  signInWithTokens: (accessToken: string) => Promise<boolean>;
  signOut: () => void;
}
const Ctx = createContext<AuthCtx | null>(null);

// Historical key: used to store the access token directly in localStorage.
// Kept only so existing users aren't logged out; read once on startup, then
// removed. Never written again.
const LEGACY_KEY = 'convener.token';

// Written by an earlier build that attempted a refresh flow. That flow was
// removed (it needed a client secret the relay deliberately does not hold), so
// the key is inert -- but an inert key nobody clears is litter in a browser we
// do not control. Cleared on startup, like the legacy token above.
const ORPHANED_REFRESH_KEY = 'convener.refresh';

function readLocalStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function removeLocalStorage(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

/** Read the legacy access-token key once, deleting it in the process so it's
 *  never consulted again. */
function consumeLegacyToken(): string | null {
  const legacy = readLocalStorage(LEGACY_KEY);
  if (legacy) removeLocalStorage(LEGACY_KEY);
  return legacy;
}

/** Synchronous part of the initial auth state: demo mode and "nothing
 *  stored" can be resolved immediately, so they're computed in the
 *  useState initialiser instead of being set from inside the effect below. */
function initialAuthState(): AuthState {
  if (isDemoMode()) return { token: 'demo', login: DEMO_USER.login, ready: true, startupError: null };
  if (readLocalStorage(LEGACY_KEY)) return { token: null, login: null, ready: false, startupError: null };
  return { token: null, login: null, ready: true, startupError: null };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [s, setS] = useState<AuthState>(initialAuthState);

  useEffect(() => {
    if (isDemoMode()) return;

    removeLocalStorage(ORPHANED_REFRESH_KEY);
    const legacy = consumeLegacyToken();
    if (!legacy) return; // initial state was already ready: true

    // validateToken never rejects (see api.ts), but this .catch is defence
    // in depth: a startup failure must always reach a terminal `ready`
    // state, never leave the app on a permanent spinner.
    validateToken(legacy)
      .then(u =>
        setS({
          token: u ? legacy : null,
          login: u?.login ?? null,
          ready: true,
          startupError: u
            ? null
            : 'You were signed out. Check your connection, then sign in again.',
        }),
      )
      .catch(() =>
        setS({
          token: null,
          login: null,
          ready: true,
          startupError: 'You were signed out. Check your connection, then sign in again.',
        }),
      );
  }, []);

  async function signIn(t: string) {
    const u = await validateToken(t);
    if (!u) return false;
    setS({ token: t, login: u.login, ready: true, startupError: null });
    return true;
  }

  /** Used by the device-flow screen: an access token from a completed
   *  sign-in. There is no refresh token to persist — see operations.md for
   *  why the refresh path was removed. */
  async function signInWithTokens(accessToken: string) {
    const u = await validateToken(accessToken);
    if (!u) return false;
    setS({ token: accessToken, login: u.login, ready: true, startupError: null });
    return true;
  }

  function signOut() {
    removeLocalStorage(LEGACY_KEY);
    exitDemoMode();
    setS({ token: null, login: null, ready: true, startupError: null });
  }

  return (
    <Ctx.Provider value={{ ...s, signIn, signInWithTokens, signOut }}>{children}</Ctx.Provider>
  );
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error('useAuth outside provider');
  return c;
}
