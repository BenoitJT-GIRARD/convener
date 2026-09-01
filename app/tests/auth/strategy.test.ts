import { describe, expect, it } from 'vitest';
import { availableStrategy } from '../../src/auth/strategy';

describe('availableStrategy', () => {
  it('uses the device flow when the relay is fully configured', () => {
    expect(
      availableStrategy({ proxyUrl: 'https://relay.example', clientId: 'Iv1.abc' }),
    ).toBe('device');
  });

  it('falls back to a token when nothing is configured', () => {
    expect(availableStrategy({})).toBe('token');
  });

  it('falls back to a token when only part is configured', () => {
    expect(availableStrategy({ proxyUrl: 'https://relay.example' })).toBe('token');
    expect(availableStrategy({ clientId: 'Iv1.abc' })).toBe('token');
  });

  it('treats blank values as unset', () => {
    expect(availableStrategy({ proxyUrl: '  ', clientId: 'Iv1.abc' })).toBe('token');
  });
});
