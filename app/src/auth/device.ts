/**
 * GitHub's OAuth device flow, driven through the CORS relay.
 *
 * The user never visits a settings page: they read a short code, type it on
 * github.com, and come back signed in.
 */

export interface DeviceCode {
  device_code: string;
  user_code: string;
  verification_uri: string;
  interval: number;
  expires_in: number;
}

export interface Tokens {
  access_token: string;
  refresh_token?: string;
  expires_in?: number;
}

export class DeviceFlowError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.name = 'DeviceFlowError';
    this.code = code;
  }
}

interface PollOptions {
  interval: number;
  sleep: (ms: number) => Promise<void>;
  maxAttempts?: number;
}

async function postJson(url: string, body: unknown): Promise<Record<string, unknown>> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    throw new DeviceFlowError(
      'unreachable',
      'Could not reach GitHub. Please check your internet connection and try again.',
    );
  }
  if (!response.ok) {
    throw new DeviceFlowError(
      `http_error_${response.status}`,
      'Sign-in is not working right now. Please try again in a moment.',
    );
  }
  try {
    return (await response.json()) as Record<string, unknown>;
  } catch {
    throw new DeviceFlowError(
      'bad_response',
      'Sign-in is not working right now. Please try again in a moment.',
    );
  }
}

export async function requestDeviceCode(
  proxyUrl: string,
  clientId: string,
): Promise<DeviceCode> {
  const data = await postJson(`${proxyUrl}/login/device/code`, {
    client_id: clientId,
    scope: 'repo',
  });
  return {
    device_code: String(data.device_code),
    user_code: String(data.user_code),
    verification_uri: String(data.verification_uri),
    interval: Number(data.interval ?? 5),
    expires_in: Number(data.expires_in ?? 900),
  };
}

// Plain-language messages for non-technical volunteers: never surface a raw
// OAuth error code as the message they see.
const MESSAGES: Record<string, string> = {
  expired_token: 'The code expired. Start again.',
  access_denied: 'Sign-in was refused on GitHub.',
  timeout: 'Sign-in timed out. Start again.',
};

// 180 attempts at the default 5s interval covers 900s (15 minutes), which
// matches GitHub's typical device-code expires_in.
const DEFAULT_MAX_ATTEMPTS = 180;

export async function pollForToken(
  proxyUrl: string,
  clientId: string,
  deviceCode: string,
  options: PollOptions,
): Promise<Tokens> {
  let interval = options.interval;
  const maxAttempts = options.maxAttempts ?? DEFAULT_MAX_ATTEMPTS;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    // Sleep before requesting: the user needs time to type the code, and
    // polling instantly would waste an attempt.
    await options.sleep(interval * 1000);

    const data = await postJson(`${proxyUrl}/login/oauth/access_token`, {
      client_id: clientId,
      device_code: deviceCode,
      grant_type: 'urn:ietf:params:oauth:grant-type:device_code',
    });

    if (typeof data.access_token === 'string') {
      return {
        access_token: data.access_token,
        refresh_token:
          typeof data.refresh_token === 'string' ? data.refresh_token : undefined,
        expires_in:
          typeof data.expires_in === 'number' ? data.expires_in : undefined,
      };
    }

    const error = String(data.error ?? '');
    if (error === 'authorization_pending') continue;
    if (error === 'slow_down') {
      interval = Number(data.interval ?? interval + 5);
      continue;
    }
    throw new DeviceFlowError(
      error,
      MESSAGES[error] ?? 'Sign-in failed. Please try again.',
    );
  }

  throw new DeviceFlowError('timeout', MESSAGES.timeout);
}
