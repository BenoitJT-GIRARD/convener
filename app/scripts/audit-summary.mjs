/**
 * Render `npm audit --json` as the table `.github/workflows/quality.yml`
 * writes into the run's own job summary.
 *
 * Run as a command it reads the report on standard input and writes
 * GitHub-flavoured markdown on standard output. It is the reporting half of a
 * step that does not block: `app/`'s blocking gate is `npm audit --omit=dev`,
 * over the packages that ship in the built cockpit, and this covers
 * everything that gate omits by design -- the compiler, the bundler, the
 * linters, the test runner. A finding there is worth knowing and is not worth
 * failing a merge over.
 *
 * **What it does with a report it cannot read.** It throws, and as a command
 * that is a non-zero exit. The two outcomes a reader has to be able to tell
 * apart are "the audit ran and found these" and "the audit did not run"; a
 * script that printed an empty table for both would make a network failure
 * look like a clean tree, which is the one reading that is certainly wrong
 * (D-25). Finding something is not a failure here. Finding nothing out is.
 */

/** Severity order, worst first, so the table reads top-down. */
const SEVERITY = ['critical', 'high', 'moderate', 'low', 'info'];

/** A cell that cannot break the table it sits in: `|` ends a cell and a
 *  newline ends the row, and an advisory title is somebody else's text. */
function cell(text) {
  return String(text).replaceAll('|', '\\|').replace(/\s+/g, ' ').trim();
}

/** What `npm` says can be done about this package, in its own terms.
 *  `fixAvailable` is `false`, `true`, or the release that would replace it. */
function fix(available) {
  if (available === false || available === undefined) return 'none published';
  if (available === true) return '`npm audit fix`';
  const major = available.isSemVerMajor ? ', a major' : '';
  return `\`${cell(available.name)}@${cell(available.version)}\`${major}`;
}

/** One row's advisories. `via` holds advisory objects for the package the
 *  advisory is against, and plain names for a package that is only reached
 *  through another one -- both are worth printing, and only the first has
 *  anywhere to link to. */
function advisories(via) {
  return (via ?? [])
    .map(entry =>
      typeof entry === 'string'
        ? `via \`${cell(entry)}\``
        : `[${cell(entry.title)}](${entry.url})`,
    )
    .join('<br>');
}

/** The count line, in the shape `npm audit`'s own last line uses. */
function counted(totals) {
  const found = SEVERITY.filter(name => totals[name] > 0).map(
    name => `${totals[name]} ${name}`,
  );
  return found.length === 0 ? 'No advisory matches this tree.' : `${found.join(', ')}.`;
}

/**
 * The markdown for one parsed report.
 *
 * Throws on anything that is not an audit: `npm audit --json` answers a
 * registry it could not reach with an object of its own, and that object has
 * no vulnerabilities in it, which is indistinguishable from a clean tree to
 * anybody reading only the count.
 */
export function auditSummary(audit) {
  const totals = audit?.metadata?.vulnerabilities;
  if (audit?.auditReportVersion !== 2 || totals === undefined) {
    throw new Error(
      'npm audit produced no report, so nothing here was audited: ' +
        `${JSON.stringify(audit).slice(0, 400)}`,
    );
  }
  const lines = [
    '### Dependency audit — `app/` development tooling',
    '',
    counted(totals),
    '',
  ];
  const packages = Object.values(audit.vulnerabilities ?? {}).sort(
    (one, other) =>
      SEVERITY.indexOf(one.severity) - SEVERITY.indexOf(other.severity) ||
      one.name.localeCompare(other.name),
  );
  if (packages.length > 0) {
    lines.push(
      '| Package | Severity | Advisory | Fix |',
      '| --- | --- | --- | --- |',
      ...packages.map(
        found =>
          `| \`${cell(found.name)}\` | ${cell(found.severity)} | ` +
          `${advisories(found.via)} | ${fix(found.fixAvailable)} |`,
      ),
      '',
    );
  }
  lines.push(
    'This step does not block. `npm audit --omit=dev`, in the step above, is',
    "`app/`'s blocking gate and covers what ships in the built cockpit; the",
    "packages listed here run on a runner or a maintainer's machine and reach",
    'no built output. The table is here so that a finding among them is still',
    'read by somebody (D-25).',
    '',
  );
  return lines.join('\n');
}

/** Read the whole of standard input. */
async function input() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString('utf8');
}

if (import.meta.main) {
  const text = await input();
  let audit;
  try {
    audit = JSON.parse(text);
  } catch (error) {
    throw new Error(
      `npm audit wrote something that is not JSON (${error.message}): ` +
        `${text.slice(0, 400)}`,
    );
  }
  process.stdout.write(auditSummary(audit));
}
