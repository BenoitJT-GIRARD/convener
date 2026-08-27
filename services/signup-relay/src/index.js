/**
 * The point of entry for a registration: `app/src/signup/SignupForm.tsx`
 * encrypts a participant's answers in the browser (`encrypt.ts`) and POSTs
 * the envelope here. This worker never sees plaintext -- it cannot, by
 * construction: the browser holds only the event's *public* half of an
 * RSA-2048 key pair (`tools/convener_ops/eventkeys.py`), which can encrypt but
 * not decrypt. What reaches this worker is `{event_id, v, encrypted_key,
 * iv, ciphertext}`, and every field but `event_id` is base64 ciphertext.
 * See README.md for what that does and does not let this worker verify.
 *
 * Unlike services/form-relay, there is no shared secret a caller signs
 * with -- a static page cannot hold one -- so this endpoint is open by
 * construction. README.md ("Abuse protection") records the choice made for
 * that and why -- a per-event burst limiter, a per-event cumulative
 * ceiling, and a global burst limiter on
 * top of the per-event one, closing the gap a caller who varies event_id
 * could otherwise use to evade it entirely -- each with its own storage
 * binding. Unlike services/auth-proxy,
 * this worker holds a GitHub token (turning a submission into a
 * repository_dispatch requires one), so it cannot be secret-free either --
 * see README.md for why that puts it in its own worker rather than a route
 * on either of the other two.
 *
 * It answers cross-origin requests -- the form is served from a different
 * origin than this worker -- following the same pattern
 * `services/auth-proxy/src/index.js` already uses: an `ALLOWED_ORIGIN`
 * check, a preflight answer, and CORS headers on every response, error or
 * not, so a caller can actually read what this worker sends back.
 *
 * It logs no request body and keeps nothing beyond the per-event counters
 * README.md describes -- and a counter is a count, never the data that
 * produced it.
 *
 * A second route, not a second worker
 * -----------------------------------
 * `POST /survey` accepts a post-event survey response -- `app/src/survey/
 * SurveyForm.tsx` and `app/src/survey/encrypt.ts`, the sibling of the
 * registration page and its own `encrypt.ts`. It is the *same* worker, not
 * a fourth one, because the survey travels through the same entry point
 * as registration: the envelope this worker validates is
 * byte-identical in shape (`validatedEventId` below makes no distinction
 * between the two routes at all), the known-event check is the same lookup
 * against the same `keys/events/<id>.pub`, and the GitHub token is the
 * same one already scoped to this repository. Splitting that into a second
 * deployment would buy nothing this worker's own reasoning for being a
 * *third* worker (see "Why this is a third worker" below) actually asked
 * for -- there is no second trust boundary here.
 *
 * Where the two routes *do* part company is what they do with an accepted
 * body. `/survey` always writes the envelope to
 * the `submission-queue` branch and starts nothing at all: a survey
 * response sends nothing back to anybody, so waiting for the daily drain
 * costs the person who submitted it precisely nothing.
 *
 * `/` has two lanes, and **the distance to the event is the only thing that
 * chooses between them**. The confirmation e-mail a registration
 * produces is not a receipt, it is the entry ticket -- it carries the room
 * link and the matching code, and there is no other channel for either --
 * so a fixed delay is out. Further from the event than the published
 * cutoff: the envelope goes in the same queue, and no run starts. Closer
 * than it: the `registration-submitted` dispatch goes out exactly as it
 * always did, `registration.yml` runs, and the confirmation is in the
 * registrant's inbox within the minute. Same cost as before, same latency.
 *
 * The cutoff is not computed here. `registrationCutoff` reads one
 * already-resolved instant per event out of
 * `public-data/registration-routing.json`, which
 * `tools/convener_ops/registration_routing.py` produces and `deploy.yml`
 * commits, so every part of the rule with a project decision in it --
 * Europe/Paris, the standing start, the configured threshold and the floor
 * under it -- lives on the side that has tests and fixtures for it. This
 * worker's whole share is one comparison against the clock.
 *
 * **An unreadable answer means "dispatch now", never "queue".** That is the
 * opposite direction from `surveyEnabled` below, which fails closed, and
 * the asymmetry is deliberate: there, the risk is storing an answer nobody
 * asked for, so silence must mean no; here, the risk is a participant who
 * never receives the only message carrying their way into the room, so
 * silence must mean send it now. Guessing wrong in this direction costs one
 * billed workflow run.
 *
 * See `queueSubmission` below, and docs/reference/operations.md's
 * "Draining the submission queue".
 *
 * What *is* separate is the abuse ceiling: `/survey` gets its own KV
 * counter key and its own rate-limiter key (`surveyCounterKey`,
 * `surveyRateLimiterKey` below), so a flooded survey cannot spend a
 * registration's budget or vice versa -- the same per-event isolation the
 * existing counter already gives one event over another, applied a second
 * time across the two routes. See README.md, "A second route, not a second
 * worker" for the full reasoning.
 */

const ROUTE = '/';
const SURVEY_ROUTE = '/survey';
const USER_AGENT = 'convener-signup-relay';

/**
 * The GitHub REST root of the repository this deploy was given, and the
 * four addresses taken off it. Built from a binding, never written out
 * here.
 *
 * `owner/name` is what `config/instance.json` declares, and it reaches
 * `handle` as `env.REPOSITORY`:
 * `.github/workflows/deploy-signup-relay.yml` reads the declaration
 * through the reader that owns it and passes the answer to `wrangler
 * deploy --var`. `wrangler.toml`'s own header carries the reasoning, and
 * `services/auth-proxy/wrangler.toml`'s carries it in full for the
 * origin this followed.
 *
 * Nothing here checks the shape. `published.identity_from_data` refuses
 * anything that is not `owner/name`, at the one place that can see the
 * declaration; this worker's share is the question it already asks of
 * every other binding -- is it there at all.
 */
function repositoryApi(repository) {
  return `https://api.github.com/repos/${repository}`;
}

function dispatchUrl(repository) {
  return `${repositoryApi(repository)}/dispatches`;
}

/** One path under the repository's Contents API. `path` is already
 *  escaped by its caller -- `encodeURIComponent` for a single segment,
 *  `encodeURI` for a queue entry's several -- because what needs
 *  escaping differs between them. */
function contentsUrl(repository, path) {
  return `${repositoryApi(repository)}/contents/${path}`;
}

// Where a survey response goes instead of straight to a
// `repository_dispatch`. Mirrors `tools/convener_ops/submission_queue.py`'s own
// QUEUE_BRANCH / QUEUE_DIR / SURVEY_KIND, which the drain reads from -- a
// branch name that disagreed between the two would be a queue nothing ever
// drains, with nothing red anywhere to say so.
//
// A branch, never a path on the default branch: `register.yml`,
// `quality.yml` and `security.yml` start on *any* commit to the default
// branch with no path filter at all, and this worker writes with its own
// token rather than a job's GITHUB_TOKEN, so GitHub's recursion guard does
// not apply to what it pushes. A queue file on the default branch would
// bill at least five runs per submission -- the exact inverse of why this
// exists. Nothing is triggered by a push to any other branch, and that is
// held by `tools/tests/test_workflows.py`'s directory-wide sweep rather
// than by anybody remembering.
const QUEUE_BRANCH = 'submission-queue';
const QUEUE_DIR = 'queue';
// The two kinds the queue carries, mirroring `submission_queue.KINDS`. A
// closed pair here as it is there: the drain refuses an entry under any
// other directory rather than guessing what to do with it.
const SURVEY_KIND = 'survey';
const REGISTRATION_KIND = 'registration';

// The branch the queue branch is created from, the one time it does not
// exist yet. Written out here, unlike the repository above: this worker
// has no repository-metadata call to derive it from, and adding one would
// cost an API call on every submission to save one on the first. Nor is a
// deploy-time binding the answer: a default branch is the product's own
// convention, the same for every instance, not something a duplicate
// declares.
const DEFAULT_BRANCH = 'main';

function refUrl(repository) {
  return `${repositoryApi(repository)}/git/ref/heads/${DEFAULT_BRANCH}`;
}

function refsUrl(repository) {
  return `${repositoryApi(repository)}/git/refs`;
}

// Mirrors `registration_routing.ROUTING_PATH` and
// `ROUTING_FILE_VERSION`; a version this worker does not know is read as
// "no answer", which routes to the immediate lane rather than guessing at a
// shape somebody changed.
const ROUTING_PATH = 'public-data/registration-routing.json';
const ROUTING_FILE_VERSION = 1;

//: Mirrors tools/convener_ops/eventkeys.py -- see that module's docstring for why
//: these are exactly these numbers, not approximations.
const WIRE_VERSION = 1;
const RSA_ENCRYPTED_KEY_BYTES = 256; // 2048-bit modulus / 8, RSA_KEY_BITS in eventkeys.py
const GCM_NONCE_BYTES = 12;
const MIN_CIPHERTEXT_BYTES = 16; // the GCM tag alone, an empty registration
// Comfortably above any real registration (five short fields) plus its
// GCM tag and JSON overhead, and far below anything worth reading into
// memory just to reject -- see README.md's "What 'shape' means here".
const MAX_CIPHERTEXT_BYTES = 16_384;
// A pre-parse guard on the whole request body, checked before it is even
// read: an id, four base64 fields at their bounds above, and JSON
// punctuation stay well under this. Exists so an oversized body is refused
// without first being pulled fully into memory.
const MAX_BODY_BYTES = 32_768;

//: Mirrors tools/convener_ops/commit_format._TOKEN (`[A-Za-z0-9][A-Za-z0-9._-]*`),
//: the same shape an event id already has to satisfy there -- imported by
//: reference, not copied byte for byte, because the two languages cannot
//: share one regex object. Length-capped at 64: no event id in this project
//: is remotely close to that, and the cap exists only so a pathological
//: input cannot inflate the GitHub API URL or the dispatch payload it
//: participates in.
const EVENT_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;

// A per-event *cumulative* registration ceiling, needed regardless of
// whichever burst protection sits in front of it (README.md): an event
// does not have ten thousand registrants, and a count that goes past this
// is worth surfacing as a signal even where it is not, on its own, a hard
// defence. 500 is generous -- an order of magnitude above any real
// seminar's attendance -- while three orders of magnitude below "ten
// thousand". This is a *total*, unbounded in time; SIGNUP_RATE_LIMITER
// below is what bounds *velocity*, and the two are complementary, not
// redundant -- see README.md, "Abuse protection".
const PER_EVENT_CEILING = 500;

// GitHub's own dispatches/contents API has no documented timeout of its
// own, so an unresponsive upstream would otherwise hold this worker's
// invocation open until the *caller's* timeout -- SUBMIT_TIMEOUT_MS in
// app/src/signup/SignupForm.tsx -- fires instead. Both outbound GitHub
// calls carry this, well inside that 15-second client budget even if both
// were to time out in sequence.
const GITHUB_FETCH_TIMEOUT_MS = 5_000;

const EXPECTED_FIELDS = ['ciphertext', 'encrypted_key', 'event_id', 'iv', 'v'];

/** The CORS headers on every response once `ALLOWED_ORIGIN` is known to
 *  match -- mirrors `services/auth-proxy/src/index.js` exactly, including
 *  attaching them to *error* responses (a caller's `fetch` cannot read a
 *  204, or a 4xx/502 body, without `Access-Control-Allow-Origin` on that
 *  specific response, not only on success). */
function corsHeaders(origin) {
  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Accept',
    'Access-Control-Max-Age': '86400',
    Vary: 'Origin',
  };
}

/** `new Response`, always carrying the CORS headers -- one call site so no
 *  branch below this line can forget them and produce a response a real
 *  browser silently discards. */
function respond(status, env, body = null, extraHeaders = {}) {
  return new Response(body, {
    status,
    headers: { ...corsHeaders(env.ALLOWED_ORIGIN), ...extraHeaders },
  });
}

/** Decodes standard-alphabet base64 to bytes, or `null` for anything that
 *  is not validly formed -- wrong alphabet, wrong padding, or a string
 *  `atob` itself refuses. Never throws. */
function base64Decode(value) {
  if (typeof value !== 'string' || value.length === 0) return null;
  if (value.length % 4 !== 0 || !/^[A-Za-z0-9+/]+={0,2}$/.test(value)) return null;
  let binary;
  try {
    binary = atob(value);
  } catch {
    return null;
  }
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

/**
 * True if `rawBody` -- already confirmed to be valid JSON describing a flat
 * object -- spells the same key twice. `JSON.parse` silently keeps only the
 * *last* occurrence of a duplicate key, so `Object.keys` on the *parsed*
 * result can never see this: two `"event_id"` entries collapse to the one
 * key this worker validates, while `client_payload.body` still forwards
 * both, byte for byte, to whatever parses it next -- which may not resolve
 * the same collision the same way `JSON.parse` did here.
 *
 * Sound rather than approximate, because every field this worker accepts
 * is a string or a number, never a nested object or array (enforced
 * elsewhere): with no legal `{...}` inside any value, an unescaped
 * `"name":` sequence anywhere in the raw text can only be an actual
 * top-level key. Inside a JSON string, an unescaped `"` always terminates
 * the string, so the same literal, unescaped sequence could never appear as
 * content instead.
 */
function hasDuplicateKey(rawBody) {
  const seen = new Set();
  const keyPattern = /"((?:[^"\\]|\\.)*)"\s*:/g;
  let match;
  while ((match = keyPattern.exec(rawBody)) !== null) {
    if (seen.has(match[1])) return true;
    seen.add(match[1]);
  }
  return false;
}

/**
 * The shape check the file-level comment promises, and nothing more: field
 * presence, exact field set (no stray extra key), plausible types and
 * lengths, and an event id shaped like one. It cannot and does not inspect
 * what `ciphertext` decrypts to -- there is no key here that could.
 *
 * Returns the validated `event_id` on success, `null` on any failure --
 * deliberately not which check failed, the same "one failure mode, no
 * oracle" reasoning `eventkeys.DecryptionError` documents for the job that
 * actually decrypts this later.
 */
function validatedEventId(parsed) {
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) return null;

  const keys = Object.keys(parsed).sort();
  if (keys.length !== EXPECTED_FIELDS.length || !EXPECTED_FIELDS.every((k, i) => keys[i] === k)) {
    return null;
  }

  const { event_id: eventId, v, encrypted_key: encryptedKey, iv, ciphertext } = parsed;

  if (typeof eventId !== 'string' || !EVENT_ID_RE.test(eventId)) return null;
  if (v !== WIRE_VERSION) return null;

  const keyBytes = base64Decode(encryptedKey);
  if (!keyBytes || keyBytes.length !== RSA_ENCRYPTED_KEY_BYTES) return null;

  const ivBytes = base64Decode(iv);
  if (!ivBytes || ivBytes.length !== GCM_NONCE_BYTES) return null;

  const cipherBytes = base64Decode(ciphertext);
  if (!cipherBytes || cipherBytes.length < MIN_CIPHERTEXT_BYTES) return null;
  if (cipherBytes.length > MAX_CIPHERTEXT_BYTES) return null;

  return eventId;
}

/**
 * Whether `keys/events/<eventId>.pub` exists in the repository -- the
 * "is this a known event" check, alongside the field checks above. Reuses `token`, the same GitHub credential the dispatch
 * below sends with: the "Contents: read & write" scope README.md documents
 * already covers a read. No second secret, no second account.
 *
 * Throws on anything other than a clean 200 or 404 -- a rate limit, a bad
 * token, GitHub unreachable, a timeout -- so the caller reports that as
 * this worker's own failure (502) rather than confusing it with "no such
 * event" (404).
 */
async function eventKeyExists(eventId, token, repository) {
  const url = contentsUrl(repository, `keys/events/${encodeURIComponent(eventId)}.pub`);
  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'User-Agent': USER_AGENT,
    },
    signal: AbortSignal.timeout(GITHUB_FETCH_TIMEOUT_MS),
  });
  if (res.status === 200) return true;
  if (res.status === 404) return false;
  throw new Error(`unexpected status checking event key: ${res.status}`);
}

/** Decodes the base64 GitHub's Contents API returns in a `content` field --
 *  distinct from `base64Decode` above, which is deliberately strict
 *  because it validates a *stranger's* untrusted ciphertext field. This
 *  input is GitHub's own API response, not a caller's: GitHub line-wraps
 *  `content` at 60 characters with embedded newlines, so stripping
 *  whitespace before decoding is correct here, not a laxness that would
 *  be wrong above. Still never throws -- a malformed response is exactly
 *  as "this worker could not get a clean answer" as any other shape this
 *  function's callers already treat that way. */
function base64DecodeContentsApi(value) {
  if (typeof value !== 'string') return null;
  try {
    const binary = atob(value.replace(/\s/g, ''));
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes;
  } catch {
    return null;
  }
}

/**
 * Whether `eventId` currently has the post-event survey switch on --
 * checked only on `/survey`, never on `/`.
 *
 * Reads `public-data/survey-status.json` through the
 * GitHub Contents API against *this* repository -- the same credential
 * (`token`) and the same call shape `eventKeyExists` already uses for
 * `keys/events/<id>.pub`, just a different path -- rather than a second
 * URL on the published site. That URL (`env.SURVEY_STATUS_URL`)
 * depended on a deployment this project has never actually wired up,
 * carried a build-to-live latency this repository's own commit does not,
 * and was a hardcoded cross-origin literal nothing derived. Reading the
 * repository's own copy makes this worker's answer agree with the
 * handler's (`tools/convener_ops/cli.py::_survey_enabled`, which reads
 * `data/speakers.yml` directly) by construction, at the cost this
 * function accepts: one more Contents-API read on a route already
 * spending one (`eventKeyExists`, just above) and already ceiling-capped
 * at `PER_EVENT_CEILING` per event.
 *
 * `public-data/survey-status.json` is committed on purpose (see
 * `.gitignore`'s own comment): a bare, sorted list of event ids, no
 * personal data, generated by `tools/convener_ops/cli.py::survey_status_
 * public_data` and pushed back to this repository by `deploy.yml`'s own
 * "Commit survey status" step.
 *
 * Throws on anything the caller cannot read as a clean, definite
 * "enabled" or "not enabled" -- a non-200/404 status, a network failure,
 * a `content` field that will not base64-decode, or decoded JSON that is
 * not an array -- so the caller reports that as this worker's own
 * failure (502), the same "ambiguous is not false" split `eventKeyExists`
 * draws for its own read. A 404 (the file does not exist, e.g. before the
 * very first "Commit survey status" run ever lands) reads as "no event is
 * open", not as an error -- the file's *absence* is exactly as valid an
 * answer as an empty array inside it.
 *
 * A caller that *did* get a definite answer and it was "not enabled"
 * reads that as `false`, refused as 404 -- the same bucket "no such
 * event" already falls into, and for the identical reason: this worker's
 * caller cannot tell the two apart from the outside and does not need to.
 *
 * This is the relay's own layer of the switch, not the only one: a page
 * that skipped this check entirely and posted straight to this route
 * would still be refused here, and the daily drain
 * (`tools/convener_ops/submission_queue.py`) checks again regardless -- this
 * check is a courtesy that saves a wasted queue entry, never the
 * authority.
 */
async function surveyEnabled(eventId, token, repository) {
  const url = contentsUrl(repository, 'public-data/survey-status.json');
  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'User-Agent': USER_AGENT,
    },
    signal: AbortSignal.timeout(GITHUB_FETCH_TIMEOUT_MS),
  });
  if (res.status === 404) return false;
  if (res.status !== 200) {
    throw new Error(`unexpected status fetching survey status: ${res.status}`);
  }
  const body = await res.json();
  const bytes = base64DecodeContentsApi(body && body.content);
  if (!bytes) {
    throw new Error('survey status file did not decode as base64');
  }
  let ids;
  try {
    ids = JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    throw new Error('survey status file was not valid JSON');
  }
  if (!Array.isArray(ids)) {
    throw new Error('survey status file was not a JSON array');
  }
  return ids.includes(eventId);
}

function counterKey(eventId) {
  return `count:${eventId}`;
}

/** The survey's own cumulative-ceiling counter key -- deliberately distinct
 *  from `counterKey`'s (`count:<id>` vs `count:survey:<id>`) rather than a
 *  shared prefix scheme, specifically so an event's *existing*, already
 *  live `count:<id>` registration counter is untouched: no in-flight
 *  registration count is renumbered or reset by this route. */
function surveyCounterKey(eventId) {
  return `count:survey:${eventId}`;
}

/** The survey's own burst-limiter key -- distinct from the bare `eventId`
 *  `SIGNUP_RATE_LIMITER` is keyed by for registration, for the identical
 *  reason `surveyCounterKey` is distinct from `counterKey`: one event's
 *  survey burst must not spend, or be blocked by, that same event's
 *  registration burst budget. */
function surveyRateLimiterKey(eventId) {
  return `survey:${eventId}`;
}

// The per-event/per-route keys above
// (`eventId`, `surveyRateLimiterKey`) are exactly what let this limiter be
// evaded -- a caller who varies event_id on every request gets a fresh
// bucket every time, so SIGNUP_RATE_LIMITER never actually bounds a flood
// that spreads itself across many fabricated ids. Fabricated ids cannot
// reach a dispatch (`eventKeyExists` below refuses them with 404), but
// each one still spends a real GitHub Contents-API call against this
// worker's own shared token budget before that refusal -- degrading
// service for real registrants on real events, whose calls draw from the
// identical pool. GLOBAL_RATE_LIMITER_KEY is one fixed literal, checked on
// a second, independent binding (GLOBAL_RATE_LIMITER, wrangler.toml) with
// its own, higher ceiling -- see README.md, "Abuse protection", for why a
// second binding rather than a second key on the same one: Cloudflare's
// Workers Rate Limiting binding applies one limit/period to every key it
// is asked about, so a global ceiling distinct from the per-event one
// needs a binding of its own.
const GLOBAL_RATE_LIMITER_KEY = 'global';

/**
 * Base64 for the Contents API's own `content` field, over the request
 * body's real UTF-8 bytes.
 *
 * Distinct from `base64Decode` above (which reads a stranger's field) and
 * from `base64DecodeContentsApi` (which reads GitHub's answer): this one
 * *writes*, and it has to write the exact bytes the drain will decrypt.
 * `btoa` alone would throw on any code point above U+00FF. Every field
 * this worker accepts is ASCII by construction, so that should be
 * unreachable -- which is precisely why it is encoded properly rather than
 * assumed away: a body that reached here with a multi-byte character would
 * otherwise become an uncaught exception and workerd's own generic error
 * page, outside the closed set of statuses this worker promises.
 */
function base64EncodeUtf8(text) {
  const bytes = new TextEncoder().encode(text);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

/**
 * One queue entry's path:
 * `queue/<kind>/<milliseconds, base36>-<uuid>.json`, matching
 * `submission_queue.entry_path` and `submission_queue.ENTRY_ID_RE`.
 *
 * The timestamp is what gives the drain a total order over everything it
 * finds -- two responses handled in one drain must land in the order they
 * would have landed in two -- and it is padded to a fixed width so that
 * ordering the *names* as strings and ordering the milliseconds as numbers
 * are the same thing. The uuid is what keeps two submissions in the same
 * millisecond from colliding on one filename, and it is also why the drain
 * can be sure a cleared entry's name will never come back: the ledger's
 * pruning rule rests on that.
 *
 * No date is read out of this by anything, ever -- the drain treats an
 * entry id as an opaque, comparable string (`submission_queue`'s own
 * module docstring). That is why using the wall clock here is not the
 * "implicit today" this project forbids elsewhere: nothing derives a Paris
 * calendar day, a deadline or a retention date from it.
 */
function queueEntryPath(kind) {
  const stamp = Date.now().toString(36).padStart(9, '0');
  return `${QUEUE_DIR}/${kind}/${stamp}-${crypto.randomUUID()}.json`;
}

/** One Contents-API write of `body` to `path` on the queue branch. */
function putQueueEntry(path, body, token, repository, kind) {
  return fetch(contentsUrl(repository, encodeURI(path)), {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'Content-Type': 'application/json',
      'User-Agent': USER_AGENT,
    },
    body: JSON.stringify({
      // Read by a person opening the branch, and it is the one place the
      // precondition can be written where somebody about to break it might
      // see it: an open pull request whose head is this branch would start
      // six workflows per submission.
      message: `queue: a ${kind} submission -- never open a pull request from ${QUEUE_BRANCH}`,
      content: base64EncodeUtf8(body),
      branch: QUEUE_BRANCH,
    }),
    signal: AbortSignal.timeout(GITHUB_FETCH_TIMEOUT_MS),
  });
}

/**
 * Create the queue branch at the default branch's current tip, for the one
 * submission in this repository's life that arrives before it exists.
 *
 * `true` only when the branch is there afterwards -- which includes a 422,
 * GitHub's answer when the reference already exists: two submissions
 * racing to create it is a success for both, not a failure for the loser.
 *
 * Needs no privilege beyond the `Contents: read & write` this worker
 * already holds for `repository_dispatch` (docs/reference/operations.md).
 * That is the ceiling this design was built against, not a starting point:
 * a queue that had needed more would have been the wrong shape.
 */
async function createQueueBranch(token, repository) {
  const headers = {
    Authorization: `Bearer ${token}`,
    Accept: 'application/vnd.github+json',
    'Content-Type': 'application/json',
    'User-Agent': USER_AGENT,
  };
  const ref = await fetch(refUrl(repository), {
    headers,
    signal: AbortSignal.timeout(GITHUB_FETCH_TIMEOUT_MS),
  });
  if (!ref.ok) return false;
  let sha;
  try {
    const data = await ref.json();
    sha = data && data.object && data.object.sha;
  } catch {
    return false;
  }
  if (typeof sha !== 'string' || sha.length === 0) return false;
  const created = await fetch(refsUrl(repository), {
    method: 'POST',
    headers,
    body: JSON.stringify({ ref: `refs/heads/${QUEUE_BRANCH}`, sha }),
    signal: AbortSignal.timeout(GITHUB_FETCH_TIMEOUT_MS),
  });
  return created.status === 201 || created.status === 422;
}

/**
 * Put one survey response in the queue, and answer with whatever GitHub
 * answered -- the caller reads `.ok` exactly as it reads the dispatch
 * call's, so a queue write that did not land is a 502 to the submitter and
 * never a silent loss.
 *
 * One API call in the ordinary case, the same count the dispatch it
 * replaces spent. The three-call path below happens once: GitHub answers a
 * write to a branch that does not exist with 404 (and, on some shapes,
 * 422), so both are read as "the branch may be missing", the branch is
 * created, and the write is retried exactly once. A second failure is
 * returned as-is rather than retried again -- a submitter learning
 * immediately that it did not work, and re-submitting, is a better outcome
 * than this worker holding their request open.
 */
async function queueSubmission(body, token, repository, kind) {
  const path = queueEntryPath(kind);
  const first = await putQueueEntry(path, body, token, repository, kind);
  if (first.status !== 404 && first.status !== 422) return first;
  if (!(await createQueueBranch(token, repository))) return first;
  return putQueueEntry(path, body, token, repository, kind);
}

/**
 * The instant `eventId` stops being far enough from its own event for a
 * registration to wait for the daily drain, in epoch milliseconds -- or
 * `null` for every answer this worker could not read as exactly that.
 *
 * `null` is not an error path with a hole in it, it is the answer: the
 * caller routes it to the immediate lane, which is what every registration
 * did before this existed. A 404 (nothing has ever been published), a rate
 * limit, an unreachable GitHub, a body that will not decode, a version this
 * worker does not know, an event absent from the file, a timestamp that
 * will not parse -- all of them mean "this worker does not know how far
 * away that event is", and the safe answer to that is to send the
 * confirmation now. See the file-level comment for why that is the opposite
 * of `surveyEnabled`'s fail-closed direction, and correctly so for each.
 *
 * Never throws, for the same reason: there is no failure here worth
 * refusing a registration over.
 */
async function registrationCutoff(eventId, token, repository) {
  let res;
  try {
    res = await fetch(contentsUrl(repository, ROUTING_PATH), {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github+json',
        'User-Agent': USER_AGENT,
      },
      signal: AbortSignal.timeout(GITHUB_FETCH_TIMEOUT_MS),
    });
  } catch {
    return null;
  }
  if (res.status !== 200) return null;
  let body;
  try {
    body = await res.json();
  } catch {
    return null;
  }
  const bytes = base64DecodeContentsApi(body && body.content);
  if (!bytes) return null;
  let data;
  try {
    data = JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    return null;
  }
  if (!data || typeof data !== 'object' || data.v !== ROUTING_FILE_VERSION) return null;
  const cutoffs = data.queue_until;
  if (!cutoffs || typeof cutoffs !== 'object') return null;
  // `Object.prototype.hasOwnProperty.call`, never `cutoffs[eventId]` alone:
  // an event id of `constructor` or `toString` would otherwise read a
  // function off the prototype chain and reach `Date.parse` as something
  // that is not a timestamp at all. `EVENT_ID_RE` does not exclude either
  // word.
  if (!Object.prototype.hasOwnProperty.call(cutoffs, eventId)) return null;
  const value = cutoffs[eventId];
  if (typeof value !== 'string') return null;
  const at = Date.parse(value);
  return Number.isFinite(at) ? at : null;
}

/**
 * `'queue'` or `'immediate'` for one arriving registration -- the JavaScript
 * twin of `registration_routing.lane`, and the whole of this worker's share
 * of the rule.
 *
 * The boundary is closed on the immediate side: a registration arriving at
 * exactly the cutoff is dispatched, not queued. An off-by-one at a boundary
 * has to fall on the side that still delivers the link.
 */
function registrationLane(cutoff, now) {
  if (cutoff === null) return 'immediate';
  return now < cutoff ? 'queue' : 'immediate';
}

export async function handle(request, env) {
  // CORS, first: the in-repo pattern services/auth-proxy/src/index.js
  // uses, copied rather than reinvented. A mismatched or absent Origin
  // gets a bare 403 with no CORS headers at all -- exactly like that
  // worker -- because a real browser sending the wrong Origin would not be
  // able to read a CORS-headed response as this worker's own origin
  // either, and a non-browser caller has no CORS to satisfy in the first
  // place. An unset ALLOWED_ORIGIN var behaves the same way: `origin` can
  // never literally equal `undefined`, so every request is refused, the
  // same fail-closed direction as the checks further down.
  const origin = request.headers.get('Origin');
  if (origin !== env.ALLOWED_ORIGIN) {
    return new Response('Forbidden', { status: 403 });
  }

  if (request.method !== 'OPTIONS' && request.method !== 'POST') {
    return respond(405, env, 'Method Not Allowed');
  }

  const { pathname } = new URL(request.url);
  if (pathname !== ROUTE && pathname !== SURVEY_ROUTE) {
    return respond(404, env, 'Not Found');
  }
  const isSurvey = pathname === SURVEY_ROUTE;

  if (request.method === 'OPTIONS') {
    // The preflight a browser sends before the real POST, because
    // `content-type: application/json` is not a CORS-safelisted value
    // (SignupForm.tsx's own submit call sets it). No body, 204, and the
    // same CORS headers every other response carries.
    return respond(204, env);
  }

  // Cheap, pre-parse guard: refuse an oversized body before it is even
  // read into memory, when the caller was honest enough to say how big it
  // is. The authoritative check is the per-field length check below --
  // this only saves the work of reading and parsing something that can
  // never pass it.
  const declaredLength = request.headers.get('content-length');
  if (declaredLength && Number(declaredLength) > MAX_BODY_BYTES) {
    return respond(400, env, 'Bad Request');
  }

  // Read raw: it contains ciphertext, and this worker cannot read it, that
  // is the point. It is parsed only far enough to check shape, then
  // forwarded byte-identical -- never re-serialised -- as
  // `client_payload.body`, the same pattern services/form-relay uses.
  // Guarded: an aborted or malformed request body throws here rather than
  // resolving, and an uncaught throw would escape as workerd's own generic
  // error page -- outside the closed set of statuses this worker promises.
  let body;
  try {
    body = await request.text();
  } catch {
    return respond(400, env, 'Bad Request');
  }

  // `body.length` is UTF-16 code units, not bytes -- a multi-byte-heavy
  // body could pass a byte-denominated MAX_BODY_BYTES compared against
  // that count. `TextEncoder` gives the real encoded byte length, the same
  // unit `MAX_BODY_BYTES` and the Content-Length check above are in.
  if (new TextEncoder().encode(body).length > MAX_BODY_BYTES) {
    return respond(400, env, 'Bad Request');
  }

  let parsed;
  try {
    parsed = JSON.parse(body);
  } catch {
    return respond(400, env, 'Bad Request');
  }

  // Checked on the *raw text*, not the parsed object: see hasDuplicateKey's
  // own docstring for why a duplicate key is invisible to any check that
  // only looks at `parsed`.
  if (hasDuplicateKey(body)) {
    return respond(400, env, 'Bad Request');
  }

  const eventId = validatedEventId(parsed);
  if (!eventId) {
    return respond(400, env, 'Bad Request');
  }

  // Fail closed: this worker is the internet-facing boundary, so an
  // unconfigured secret or an unbound store refuses every request rather
  // than silently skipping the checks they exist for -- see README.md,
  // "Fail closed, not open", for why that is the opposite of how
  // tools/convener_ops/proposal.py treats its own absent secret, and correctly
  // so for each. Checked before anything below touches GitHub or either
  // counter, so none of them is ever reached on a misconfigured deploy.
  const token = env.CONVENER_DISPATCH_TOKEN;
  // REPOSITORY joins the fail-closed set, and it is the member whose
  // absence would be quietest of the five. Every other one is missing
  // something; an unset repository is *present and wrong*, and it fails
  // in the one direction a caller cannot tell from a correct answer: a
  // Contents-API read with the word `undefined` where the repository
  // belongs is a clean 404, which `eventKeyExists` reads as "no such
  // event". Every real registration for every real event would then be
  // refused with this worker's own 404 -- the answer a stranger guessing
  // at event ids gets -- and nothing anywhere would say the relay is
  // pointed at nothing. Refused by name, before a call is spent.
  const repository = env.REPOSITORY;
  const kv = env.SIGNUP_RELAY_KV;
  const rateLimiter = env.SIGNUP_RATE_LIMITER;
  // GLOBAL_RATE_LIMITER joins the fail-closed set -- a deploy missing
  // this binding must refuse every request, the same as one missing the
  // per-event limiter, rather than silently running with only half the
  // abuse protection this worker now claims.
  const globalRateLimiter = env.GLOBAL_RATE_LIMITER;
  if (!token || !repository || !kv || !rateLimiter || !globalRateLimiter) {
    return respond(502, env, 'Bad Gateway');
  }

  // The burst limiter, checked before anything else touches GitHub or the
  // cumulative counter: purpose-built for exactly this (unlike
  // SIGNUP_RELAY_KV, a general store repurposed as a counter), keyed per
  // event so one flooded event cannot exhaust another's budget. Cloudflare
  // documents this binding as "permissive, eventually consistent, and
  // intentionally designed to not be used as an accurate accounting
  // system" -- quoted, not paraphrased, in README.md -- so a thrown
  // `.limit()` call is treated the same as any other fail-closed check
  // here: refused, not silently skipped.
  // The survey path gets its own limiter key and counter key -- see
  // surveyRateLimiterKey/surveyCounterKey's own docstrings for why a
  // flooded survey must neither spend nor be blocked by that same event's
  // registration budget.
  const rateLimiterKey = isSurvey ? surveyRateLimiterKey(eventId) : eventId;
  const eventCounterKey = isSurvey ? surveyCounterKey(eventId) : counterKey(eventId);

  // The global limiter, checked first -- one fixed key, shared by
  // both routes and every event, bounding this worker's total request
  // rate regardless of what event_id a caller sends. Checked before the
  // per-event limiter deliberately: it is the cheaper, coarser bound, and
  // it is the one a caller varying event_id cannot evade by construction,
  // so it should be the first thing an evasive flood actually meets.
  let globalLimited;
  try {
    globalLimited = await globalRateLimiter.limit({ key: GLOBAL_RATE_LIMITER_KEY });
  } catch {
    return respond(502, env, 'Bad Gateway');
  }
  if (!globalLimited.success) {
    return respond(429, env, 'Too Many Requests', { 'Retry-After': '60' });
  }

  let limited;
  try {
    limited = await rateLimiter.limit({ key: rateLimiterKey });
  } catch {
    return respond(502, env, 'Bad Gateway');
  }
  if (!limited.success) {
    return respond(429, env, 'Too Many Requests', { 'Retry-After': '60' });
  }

  // The cumulative ceiling, checked before either GitHub call: cheaper to
  // refuse here than to spend a Contents-API read and a dispatch on a
  // request that will be refused anyway. A KV read failure is treated as
  // "no count yet" rather than refusing the request -- see README.md,
  // "Abuse protection", for why an approximate ceiling is the accepted
  // trade here, not a defect. Applies identically to `/survey`: the same
  // ceiling, on the survey's own counter key -- an open path with no
  // ceiling at all would be a mailer for anyone who knows an event id.
  let count = 0;
  try {
    const stored = await kv.get(eventCounterKey);
    count = stored ? Number.parseInt(stored, 10) || 0 : 0;
  } catch {
    count = 0;
  }
  if (count >= PER_EVENT_CEILING) {
    return respond(429, env, 'Too Many Requests', { 'Retry-After': '60' });
  }

  let known;
  try {
    known = await eventKeyExists(eventId, token, repository);
  } catch {
    return respond(502, env, 'Bad Gateway');
  }
  if (!known) {
    return respond(404, env, 'Not Found');
  }

  // The relay's own layer of the survey switch,
  // checked only on `/survey` -- never on `/`, where it has no meaning --
  // and only once the event is already known to exist, so a stranger
  // guessing at event ids never learns anything new from this check that
  // the one above did not already tell them. Refused the same way an
  // unknown event is (404): the caller cannot tell "no such event" from
  // "this event has no survey open" apart, and does not need to.
  if (isSurvey) {
    let enabled;
    try {
      enabled = await surveyEnabled(eventId, token, repository);
    } catch {
      return respond(502, env, 'Bad Gateway');
    }
    if (!enabled) {
      return respond(404, env, 'Not Found');
    }
  }

  // The one place the routes part company.
  //
  // A survey response always goes in the queue: nothing is ever sent back
  // to whoever submitted it, so the slowest cadence costs them nothing.
  //
  // A registration goes in the queue only when its event is still further
  // away than the published cutoff. Closer than that -- or whenever this
  // worker could not read the cutoff at all -- it becomes the same
  // `repository_dispatch` it always was, and the confirmation carrying the
  // room link and the matching code goes out within the minute. The clock
  // is read exactly once, here, and only to compare against that cutoff:
  // nothing derives a calendar day, a deadline or a retention date from it,
  // which is the same reason `queueEntryPath` above may use `Date.now`.
  //
  // What the submitter sees is identical in every lane: 204 on success, 502
  // on anything this worker could not complete. Every refusal above this
  // line -- unknown event, closed survey, abuse ceiling -- is unchanged and
  // still immediate; the queue only ever delays what was accepted.
  let queued = isSurvey;
  if (!isSurvey) {
    queued =
      registrationLane(await registrationCutoff(eventId, token, repository), Date.now()) ===
      'queue';
  }

  let upstream;
  try {
    upstream = queued
      ? await queueSubmission(body, token, repository, isSurvey ? SURVEY_KIND : REGISTRATION_KIND)
      : await fetch(dispatchUrl(repository), {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            Accept: 'application/vnd.github+json',
            'Content-Type': 'application/json',
            'User-Agent': USER_AGENT,
          },
          // `body` is the JSON *string* read above, never a nested object:
          // the workflow that handles this reads it as a bare
          // ${{ github.event.client_payload.body }} interpolation, which
          // only renders raw JSON when the value is a string.
          body: JSON.stringify({
            event_type: 'registration-submitted',
            client_payload: { body },
          }),
          signal: AbortSignal.timeout(GITHUB_FETCH_TIMEOUT_MS),
        });
  } catch {
    // A rejected fetch -- GitHub unreachable, DNS failure, a reset
    // connection, this worker's own timeout -- is exactly as much "this
    // worker could not complete the dispatch" as a non-2xx answer below.
    return respond(502, env, 'Bad Gateway');
  }

  if (!upstream.ok) {
    // Never GitHub's status or body verbatim -- a caller with a
    // well-shaped, known-event envelope has no need to see GitHub's error
    // detail, and passing it through would blur this worker's own
    // taxonomy with GitHub's.
    return respond(502, env, 'Bad Gateway');
  }

  // Best-effort, after a confirmed dispatch: a registration that reached
  // GitHub must not be un-sent because the counter could not be written
  // afterwards -- see README.md for why this counter is a signal and not a
  // gate that must never be wrong. But a failure here is still worth a
  // trace: unlike a KV *read* failure above (indistinguishable from "no
  // registrations yet", and harmless to treat as one), a *write* failure
  // means a real, accepted registration will never be counted, which is
  // exactly the state a signal exists to surface, not hide. `console.error`
  // carries only the event id -- already public, the same identifier every
  // dispatch and every workflow run already names -- and a fixed message;
  // never the body.
  try {
    await kv.put(eventCounterKey, String(count + 1));
  } catch {
    const label = isSurvey ? 'survey response' : 'registration';
    console.error(`signup-relay: failed to update the ${label} counter for event ${eventId}`);
  }

  // Fixed 204, not upstream.status -- see services/form-relay/src/index.js
  // for why an unexpected 2xx must not leak through as-is. The caller only
  // ever sees one of 204, 400, 403, 404, 405, 429 or 502 from this worker.
  return respond(204, env);
}

export default { fetch: handle };
