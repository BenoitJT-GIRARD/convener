import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { validateToken } from './api';
import { isDemoMode, exitDemoMode, DEMO_USER } from '../data/demo';
import { authEnv, availableStrategy } from './strategy';

interface AuthState {
  token: string | null;
  login: string | null;
  ready: boolean;
}
interface AuthCtx extends AuthState {
  signIn: (t: string) => Promise<boolean>;
  signInWithTokens: (accessToken: string, refreshToken?: string) => Promise<boolean>;
  signOut: () => void;
}
const Ctx = createContext<AuthCtx | null>(null);

// Historical key: used to store the access token directly in localStorage.
// Kept only so existing users aren't logged out; read once on startup, then
// removed. Never written again.
const LEGACY_KEY = 'convener.token';

// The access token itself never touches localStorage (it's kept in React
// state only). Only the longer-lived refresh token, which is useless
// without the relay's client secret, is persisted here.
const REFRESH_KEY = 'convener.refresh';

function readLocalStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeLocalStorage(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* ignore */
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

interface ExchangedTokens {
  access_token: string;
  refresh_token?: string;
}

/** Trade a stored refresh token for a fresh access token through the relay.
 *  Only meaningful when the device flow is configured; a token-only
 *  instance never issues refresh tokens in the first place. */
async function exchangeRefreshToken(refreshToken: string): Promise<ExchangedTokens | null> {
  const env = authEnv();
  if (availableStrategy(env) !== 'device') return null;
  try {
    const response = await fetch(`${env.proxyUrl}/login/oauth/access_token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({
        client_id: env.clientId,
        grant_type: 'refresh_token',
        refresh_token: refreshToken,
      }),
    });
    if (!response.ok) return null;
    const data = (await response.json()) as Record<string, unknown>;
    if (typeof data.access_token !== 'string') return null;
    return {
      access_token: data.access_token,
      refresh_token: typeof data.refresh_token === 'string' ? data.refresh_token : undefined,
    };
  } catch {
    return null;
  }
}

/** Synchronous part of the initial auth state: demo mode and "nothing
 *  stored" can be resolved immediately, so they're computed in the
 *  useState initialiser instead of being set from inside the effect below. */
function initialAuthState(): AuthState {
  if (isDemoMode()) return { token: 'demo', login: DEMO_USER.login, ready: true };
  if (readLocalStorage(LEGACY_KEY)) return { token: null, login: null, ready: false };
  if (readLocalStorage(REFRESH_KEY)) return { token: null, login: null, ready: false };
  return { token: null, login: null, ready: true };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [s, setS] = useState<AuthState>(initialAuthState);

  useEffect(() => {
    if (isDemoMode()) return;

    const legacy = consumeLegacyToken();
    if (legacy) {
      validateToken(legacy).then(u =>
        setS({ token: u ? legacy : null, login: u?.login ?? null, ready: true }),
      );
      return;
    }

    const refreshToken = readLocalStorage(REFRESH_KEY);
    if (!refreshToken) return; // initial state was already ready: true

    exchangeRefreshToken(refreshToken).then(async exchanged => {
      if (!exchanged) {
        removeLocalStorage(REFRESH_KEY);
        setS({ token: null, login: null, ready: true });
        return;
      }
      if (exchanged.refresh_token) writeLocalStorage(REFRESH_KEY, exchanged.refresh_token);
      const u = await validateToken(exchanged.access_token);
      setS({ token: u ? exchanged.access_token : null, login: u?.login ?? null, ready: true });
    });
  }, []);

  async function signIn(t: string) {
    const u = await validateToken(t);
    if (!u) return false;
    setS({ token: t, login: u.login, ready: true });
    return true;
  }

  /** Used by the device-flow screen: an access token plus, when the relay
   *  issued one, a refresh token to persist for next time. */
  async function signInWithTokens(accessToken: string, refreshToken?: string) {
    const u = await validateToken(accessToken);
    if (!u) return false;
    if (refreshToken) writeLocalStorage(REFRESH_KEY, refreshToken);
    setS({ token: accessToken, login: u.login, ready: true });
    return true;
  }

  function signOut() {
    removeLocalStorage(LEGACY_KEY);
    removeLocalStorage(REFRESH_KEY);
    exitDemoMode();
    setS({ token: null, login: null, ready: true });
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
