import { describe, expect, it } from 'vitest';
import { formatDurationHours, asDisplayCertificate } from '../src/verify/format';
import cases from '../../tools/tests/fixtures/certificate-verification.json';

describe('formatDurationHours', () => {
  // Minor 10 (task 12, fix round 1): a naive template literal or
  // `String(hours)` collapses 2.0 to "2" -- a cosmetic mismatch against
  // what the certified document itself prints (Python's `json.dumps(2.0)`
  // is "2.0"). Every quarter-hour grain value must show its exact
  // fractional part, and a whole number must still show ".0".
  it.each([
    [0.25, '0.25'],
    [0.5, '0.5'],
    [0.75, '0.75'],
    [1, '1.0'],
    [1.25, '1.25'],
    [1.5, '1.5'],
    [1.75, '1.75'],
    [2, '2.0'],
  ])('%s hours -> %s', (hours, expected) => {
    expect(formatDurationHours(hours)).toBe(expected);
  });

  it('matches the fixture\'s own two signed examples exactly', () => {
    expect(formatDurationHours(cases.signed_example.payload_decoded.duration_hours)).toBe('1.5');
    expect(formatDurationHours(cases.integer_duration_example.payload_decoded.duration_hours)).toBe(
      '2.0',
    );
  });

  it('never crashes on a non-finite number', () => {
    expect(formatDurationHours(Number.NaN)).toBe('(not recorded)');
    expect(formatDurationHours(Number.POSITIVE_INFINITY)).toBe('(not recorded)');
  });
});

describe('asDisplayCertificate', () => {
  it('renders every field of a genuine, well-shaped payload', () => {
    const display = asDisplayCertificate(cases.signed_example.payload_decoded);
    expect(display).toEqual({
      identifier: cases.signed_example.identifier,
      event: cases.signed_example.payload_decoded.event,
      name: cases.signed_example.payload_decoded.name,
      date: cases.signed_example.payload_decoded.date,
      durationHours: '1.5',
    });
  });

  it('falls back field by field, rather than crashing, on a payload missing fields', () => {
    const display = asDisplayCertificate({});
    expect(display).toEqual({
      identifier: '(not recorded)',
      event: '(not recorded)',
      name: '(not recorded)',
      date: '(not recorded)',
      durationHours: '(not recorded)',
    });
  });

  it('falls back on fields of the wrong type without crashing', () => {
    const display = asDisplayCertificate({
      identifier: 42,
      event: null,
      name: ['not', 'a', 'string'],
      date: undefined,
      duration_hours: '1.5',
    });
    expect(display.identifier).toBe('(not recorded)');
    expect(display.event).toBe('(not recorded)');
    expect(display.name).toBe('(not recorded)');
    expect(display.date).toBe('(not recorded)');
    expect(display.durationHours).toBe('(not recorded)');
  });
});
