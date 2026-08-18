/**
 * Which sign-in method is available right now.
 *
 * A missing relay is a normal state, not an error: the application stays
 * fully usable through a personal access token, only the onboarding is
 * slower. See decision D-13.
 */

export interface AuthEnv {
  proxyUrl?: string;
  clientId?: string;
}

export type Strategy = 'device' | 'token';

function isSet(value: string | undefined): boolean {
  return Boolean(value && value.trim());
}

export function availableStrategy(env: AuthEnv): Strategy {
  return isSet(env.proxyUrl) && isSet(env.clientId) ? 'device' : 'token';
}

export function authEnv(): AuthEnv {
  return {
    proxyUrl: import.meta.env.VITE_AUTH_PROXY_URL as string | undefined,
    clientId: import.meta.env.VITE_GITHUB_APP_CLIENT_ID as string | undefined,
  };
}
