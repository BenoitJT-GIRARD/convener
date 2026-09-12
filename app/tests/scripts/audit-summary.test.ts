/**
 * `scripts/audit-summary.mjs` -- what `.github/workflows/quality.yml` writes
 * into a run's own job summary for `app/`'s development tooling.
 *
 * The step this renders for does not block, which is why where it reports
 * matters so much. It used to print to the log under `continue-on-error:
 * true`, which records the step as failed: every green run carried a red
 * annotation, and a red cross on a passing run is read as breakage once and
 * skipped ever after. So the finding is a table on the run page now, and the
 * step exits 0 on whatever it found.
 *
 * Two things are held here, and the second is the one D-25 asks for. The
 * table says what the audit found; and a report that is not an audit is
 * refused rather than rendered as an empty one. "Nothing was found" and
 * "nothing looked" are the two outcomes a summary must never make look alike,
 * and an audit that could not reach the registry answers with an object of
 * its own that has no vulnerabilities in it.
 *
 * The report below is the real one this tree produced -- `npm audit --json`
 * in `app/`, with `vitest` 4 installed, GHSA-82fw-gwwq-j7x9 and the two
 * packages it reaches.
 */
import { describe, expect, it } from 'vitest';
import { auditSummary } from '../../scripts/audit-summary.mjs';

/** `npm audit --json`, as it came out of this tree. */
const REPORT = {
  auditReportVersion: 2,
  vulnerabilities: {
    '@vitest/coverage-v8': {
      name: '@vitest/coverage-v8',
      severity: 'moderate',
      isDirect: true,
      via: ['vitest'],
      range: '2.1.0-beta.1 - 4.1.10',
      fixAvailable: true,
    },
    '@vitest/mocker': {
      name: '@vitest/mocker',
      severity: 'moderate',
      isDirect: false,
      via: [
        {
          source: 1193684,
          name: '@vitest/mocker',
          title:
            'Vitest: Path Traversal / Arbitrary File Read via @vitest/mocker Redirect Mock',
          url: 'https://github.com/advisories/GHSA-82fw-gwwq-j7x9',
          severity: 'moderate',
          range: '>=2.1.0 <4.1.11',
        },
      ],
      range: '2.1.0 - 4.1.10',
      fixAvailable: true,
    },
  },
  metadata: {
    vulnerabilities: { info: 0, low: 0, moderate: 3, high: 0, critical: 0, total: 3 },
  },
};

/** The same report with nothing in it: a tree no advisory matches. */
const CLEAN = {
  auditReportVersion: 2,
  vulnerabilities: {},
  metadata: {
    vulnerabilities: { info: 0, low: 0, moderate: 0, high: 0, critical: 0, total: 0 },
  },
};

describe('the dependency audit a run writes into its own job summary', () => {
  it('names every package the audit found, at its severity', () => {
    const summary = auditSummary(REPORT);
    expect(summary).toContain('| `@vitest/mocker` | moderate |');
    expect(summary).toContain('| `@vitest/coverage-v8` | moderate |');
  });

  it('links the advisory rather than only counting it', () => {
    expect(auditSummary(REPORT)).toContain(
      '[Vitest: Path Traversal / Arbitrary File Read via @vitest/mocker Redirect Mock]' +
        '(https://github.com/advisories/GHSA-82fw-gwwq-j7x9)',
    );
  });

  it('says what can be done about each one', () => {
    expect(auditSummary(REPORT)).toContain('`npm audit fix`');
    expect(
      auditSummary({
        ...CLEAN,
        vulnerabilities: {
          left: { name: 'left', severity: 'high', via: ['other'], fixAvailable: false },
        },
      }),
    ).toContain('none published');
  });

  it('counts what it found the way npm audit does', () => {
    expect(auditSummary(REPORT)).toContain('3 moderate.');
  });

  it('renders a table a reader can read, not a wall of log', () => {
    const summary = auditSummary(REPORT);
    expect(summary).toContain('| Package | Severity | Advisory | Fix |');
    // Every row is one line: a title carrying a newline, or a `|`, would
    // otherwise split its own row and shift every cell after it.
    const rows = summary.split('\n').filter(line => line.startsWith('| `'));
    expect(rows).toHaveLength(2);
  });

  it('says plainly that a clean tree is clean', () => {
    const summary = auditSummary(CLEAN);
    expect(summary).toContain('No advisory matches this tree.');
    expect(summary).not.toContain('| Package |');
  });

  it('keeps a title that carries a pipe inside its own cell', () => {
    const summary = auditSummary({
      ...CLEAN,
      vulnerabilities: {
        odd: {
          name: 'odd',
          severity: 'low',
          via: [{ title: 'a | b\nc', url: 'https://example.test/a' }],
          fixAvailable: true,
        },
      },
    });
    const [row] = summary.split('\n').filter(line => line.startsWith('| `odd`'));
    expect(row).toContain('a \\| b c');
    expect(summary.split('\n').filter(line => line.startsWith('| `'))).toHaveLength(1);
  });

  // The counter-proof. Each of these is what `npm audit --json` writes when
  // it did not audit anything, and each one has a vulnerability count of
  // nothing -- which is exactly what a clean tree has.
  it.each([
    ['a registry it could not reach', { error: { code: 'ENETUNREACH' } }],
    ['an empty object', {}],
    ['a report version nothing here can read', { auditReportVersion: 3 }],
    ['no report at all', null],
  ])('refuses %s rather than rendering it as a clean tree', (_name, notAnAudit) => {
    expect(() => auditSummary(notAnAudit)).toThrow(/nothing here was audited/);
  });
});
