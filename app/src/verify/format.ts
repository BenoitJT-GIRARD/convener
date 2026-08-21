/**
 * Turning a signature-confirmed, but otherwise unstructured, payload into
 * something safe to render -- and rendering its one numeric field the way
 * the certificate itself would print it.
 */
import type { CertificatePayload } from './verify';

/** What `VerifyPage` actually displays once a signature has confirmed a
 *  payload is genuine. Every field is a plain string (`durationHours` is
 *  pre-formatted, see `formatDurationHours` below) -- there is nothing
 *  left for a display component to coerce or guess the type of. */
export interface DisplayCertificate {
  readonly identifier: string;
  readonly event: string;
  readonly name: string;
  readonly date: string;
  readonly durationHours: string;
}

const FALLBACK = '(not recorded)';

function asString(value: unknown): string {
  return typeof value === 'string' && value.length > 0 ? value : FALLBACK;
}

/**
 * `duration_hours` is always a multiple of a quarter hour
 * (`certificate.duration_hours`'s own rounding grain), so up to two
 * decimal places is always exact -- 0.25, 1.5, 2.0 all round-trip through
 * IEEE-754 binary without loss, since each is a power-of-two fraction.
 * `toFixed(2)` alone would still print `2.00` for a whole number, where
 * Python's own `json.dumps(2.0)` prints `2.0` -- a *second* mismatch this
 * function exists to close, not only the `2` a bare template literal would
 * produce (see `verify.ts`'s own docstring for why the fixture pins this
 * exact number). Trimming one trailing zero, and no more, lands on
 * Python's own minimal float representation for every value this field
 * can actually hold: "2.0", "1.5", "1.25", "0.75".
 */
export function formatDurationHours(hours: number): string {
  if (!Number.isFinite(hours)) return FALLBACK;
  const fixed = hours.toFixed(2);
  return fixed.endsWith('0') ? fixed.slice(0, -1) : fixed;
}

/**
 * Best-effort coercion of a signature-confirmed payload into something
 * `VerifyPage` can render without crashing. `verify()` (see verify.ts),
 * like `signing.py::verify`, never checks that a genuinely-signed payload
 * carries exactly `signing.PAYLOAD_FIELDS` -- every payload `sign()` has
 * ever produced already does, by construction, on the Python side, but a
 * defensive display layer does not get to assume that never changes
 * without also crashing the one page a stranger relies on to read a
 * certificate. A field of the wrong shape renders as "(not recorded)"
 * rather than throwing or hiding the rest of the certificate.
 */
export function asDisplayCertificate(payload: CertificatePayload): DisplayCertificate {
  const hours = payload.duration_hours;
  return {
    identifier: asString(payload.identifier),
    event: asString(payload.event),
    name: asString(payload.name),
    date: asString(payload.date),
    durationHours: typeof hours === 'number' ? formatDurationHours(hours) : FALLBACK,
  };
}
