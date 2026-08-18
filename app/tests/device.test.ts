import { describe, expect, it, vi, beforeEach } from 'vitest';
import { DeviceFlowError, pollForToken, requestDeviceCode } from '../src/auth/device';

const PROXY = 'https://relay.example';
const CLIENT = 'Iv1.abc';

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

beforeEach(() => vi.restoreAllMocks());

describe('requestDeviceCode', () => {
  it('returns the code and the interval', async () => {
    globalThis.fetch = vi.fn(async () =>
      jsonResponse({
        device_code: 'dev-1', user_code: 'WDJB-MJHT',
        verification_uri: 'https://github.com/login/device',
        interval: 5, expires_in: 900,
      }),
    );
    const code = await requestDeviceCode(PROXY, CLIENT);
    expect(code.user_code).toBe('WDJB-MJHT');
    expect(code.interval).toBe(5);
  });

  it('throws when the relay is unreachable', async () => {
    globalThis.fetch = vi.fn(async () => { throw new TypeError('failed to fetch'); });
    await expect(requestDeviceCode(PROXY, CLIENT)).rejects.toBeInstanceOf(DeviceFlowError);
  });

  it('throws a readable DeviceFlowError when the relay returns an HTTP error', async () => {
    globalThis.fetch = vi.fn(async () => new Response('server error', { status: 502 }));
    await expect(requestDeviceCode(PROXY, CLIENT)).rejects.toMatchObject({
      code: 'http_error_502',
      message: 'Sign-in is not working right now. Please try again in a moment.',
    });
  });

  it('throws a readable DeviceFlowError when the relay returns malformed JSON', async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response('not json', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );
    await expect(requestDeviceCode(PROXY, CLIENT)).rejects.toMatchObject({
      code: 'bad_response',
      message: 'Sign-in is not working right now. Please try again in a moment.',
    });
  });
});

describe('pollForToken', () => {
  it('keeps polling while authorization is pending, then succeeds', async () => {
    const responses = [
      jsonResponse({ error: 'authorization_pending' }),
      jsonResponse({ error: 'authorization_pending' }),
      jsonResponse({ access_token: 'gho_x', refresh_token: 'ghr_y', expires_in: 28800 }),
    ];
    globalThis.fetch = vi.fn(async () => responses.shift()!);
    const sleep = vi.fn(async () => {});

    const tokens = await pollForToken(PROXY, CLIENT, 'dev-1', { interval: 5, sleep });

    expect(tokens.access_token).toBe('gho_x');
    expect(globalThis.fetch).toHaveBeenCalledTimes(3);
    expect(sleep).toHaveBeenNthCalledWith(1, 5000);
  });

  it('sleeps before each request, not after', async () => {
    const order: string[] = [];
    const responses = [
      jsonResponse({ error: 'authorization_pending' }),
      jsonResponse({ access_token: 'gho_x' }),
    ];
    globalThis.fetch = vi.fn(async () => {
      order.push('fetch');
      return responses.shift()!;
    });
    const sleep = vi.fn(async () => {
      order.push('sleep');
    });

    await pollForToken(PROXY, CLIENT, 'dev-1', { interval: 5, sleep });

    expect(order).toEqual(['sleep', 'fetch', 'sleep', 'fetch']);
  });

  it('lengthens the interval when told to slow down', async () => {
    const responses = [
      jsonResponse({ error: 'slow_down', interval: 10 }),
      jsonResponse({ access_token: 'gho_x' }),
    ];
    globalThis.fetch = vi.fn(async () => responses.shift()!);
    const sleep = vi.fn(async () => {});

    await pollForToken(PROXY, CLIENT, 'dev-1', { interval: 5, sleep });

    expect(sleep).toHaveBeenNthCalledWith(2, 10000);
  });

  it('fails with expired_token once the code has expired', async () => {
    globalThis.fetch = vi.fn(async () => jsonResponse({ error: 'expired_token' }));
    await expect(
      pollForToken(PROXY, CLIENT, 'dev-1', { interval: 1, sleep: async () => {} }),
    ).rejects.toMatchObject({ code: 'expired_token' });
  });

  it('fails with access_denied when the user refuses', async () => {
    globalThis.fetch = vi.fn(async () => jsonResponse({ error: 'access_denied' }));
    await expect(
      pollForToken(PROXY, CLIENT, 'dev-1', { interval: 1, sleep: async () => {} }),
    ).rejects.toMatchObject({ code: 'access_denied' });
  });

  it('stops at the deadline instead of polling for ever', async () => {
    globalThis.fetch = vi.fn(async () => jsonResponse({ error: 'authorization_pending' }));
    await expect(
      pollForToken(PROXY, CLIENT, 'dev-1', {
        interval: 1, sleep: async () => {}, maxAttempts: 4,
      }),
    ).rejects.toMatchObject({ code: 'timeout' });
    expect(globalThis.fetch).toHaveBeenCalledTimes(4);
  });
});
