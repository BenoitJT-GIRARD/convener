export interface ContentEntry {
  /** path under `docs/` in the repo */
  file: string;
  /** optional heading anchor (slug from `## Heading`) to scope the render */
  anchor: string | null;
}

/** The repository the handbook is kept in. Both the "edit this page" link and
 *  the attribution line under an included passage are built from it. */
export const REPO_URL = 'https://github.com/example-instance/example-cockpit';

export const CONTENT_REGISTRY: Record<string, ContentEntry> = {
  // governance
  'governance/selection-criteria': { file: 'governance/selection-criteria.md', anchor: null },
  'governance/editorial-line': { file: 'governance/editorial-line.md', anchor: null },
  'governance/editorial-board': { file: 'governance/editorial-board.md', anchor: null },
  'governance/board-rules': { file: 'governance/board-rules.md', anchor: null },
  'governance/conflict-of-interest': { file: 'governance/conflict-of-interest.md', anchor: null },
  'governance/decisions': { file: 'governance/decisions.md', anchor: null },
  // Fix round 1: linked from `governance/decisions.md` and
  // `reference/the-workspace.md` with a plain relative link, but never
  // itself registered -- so it shipped by accident under the old
  // wholesale copy, and would have 404ed under the registry-derived
  // allowlist once that accident stopped. Registered instead of
  // delinked: it is a git-derived, no-free-text audit trail of board
  // decisions (day, identifier, closed vocabulary only -- see the file's
  // own header), the same kind of governance transparency
  // `governance/decisions` already carries, not internal operational
  // detail like `reference/operations.md`.
  'governance/register': { file: 'governance/register.md', anchor: null },
  // The processing record spec §4 names (task 18): data, purpose, legal
  // basis, recipients, duration and measures for the registration,
  // attendance and certificate pipeline. Filename kept as the task brief
  // named it; every other file in this directory is named in English.
  'governance/data-protection-record': {
    file: 'governance/traitement-donnees.md',
    anchor: null,
  },

  // decisions — the architecture decision records: why the system is shaped
  // the way it is, one file per decision, `D-NN` identifiers preserved
  // because the codebase cites them by number in comments and docstrings
  // throughout. Governance rules (G-NN) are documented separately in
  // governance/board-rules.md, not here.
  'decisions/index': { file: 'decisions/index.md', anchor: null },
  'decisions/d-01': { file: 'decisions/d-01-repository-of-record.md', anchor: null },
  'decisions/d-02': { file: 'decisions/d-02-participant-data-encryption.md', anchor: null },
  'decisions/d-03': { file: 'decisions/d-03-github-app-device-flow.md', anchor: null },
  'decisions/d-04': { file: 'decisions/d-04-concurrent-writes.md', anchor: null },
  'decisions/d-05': { file: 'decisions/d-05-meeting-platform-abstraction.md', anchor: null },
  'decisions/d-06': { file: 'decisions/d-06-registration-ownership.md', anchor: null },
  'decisions/d-07': { file: 'decisions/d-07-email-channels.md', anchor: null },
  'decisions/d-08': { file: 'decisions/d-08-visuals-generated-in-ci.md', anchor: null },
  'decisions/d-09': { file: 'decisions/d-09-no-linkedin-automation.md', anchor: null },
  'decisions/d-10': { file: 'decisions/d-10-youtube-channel-ownership.md', anchor: null },
  'decisions/d-11': {
    file: 'decisions/d-11-organisation-accounts-and-vault.md',
    anchor: null,
  },
  'decisions/d-12': { file: 'decisions/d-12-no-automatic-transcription.md', anchor: null },
  'decisions/d-13': { file: 'decisions/d-13-deferred-configuration.md', anchor: null },
  'decisions/d-14': { file: 'decisions/d-14-language-boundary.md', anchor: null },
  'decisions/d-15': { file: 'decisions/d-15-publication-topology.md', anchor: null },
  'decisions/d-16': { file: 'decisions/d-16-brand-source-of-truth.md', anchor: null },
  'decisions/d-17': { file: 'decisions/d-17-typography-substitution.md', anchor: null },
  'decisions/d-18': { file: 'decisions/d-18-static-pages-with-islands.md', anchor: null },
  'decisions/d-19': { file: 'decisions/d-19-event-identifier.md', anchor: null },
  'decisions/d-20': { file: 'decisions/d-20-certificate-wire-format.md', anchor: null },
  'decisions/d-21': { file: 'decisions/d-21-certificate-lifecycle.md', anchor: null },
  'decisions/d-22': { file: 'decisions/d-22-key-destruction-not-deletion.md', anchor: null },
  'decisions/d-23': { file: 'decisions/d-23-encrypted-record-envelope.md', anchor: null },
  'decisions/d-24': {
    file: 'decisions/d-24-operator-commands-name-things.md',
    anchor: null,
  },
  'decisions/d-25': { file: 'decisions/d-25-loud-failure.md', anchor: null },
  'decisions/d-26': { file: 'decisions/d-26-verify-deployed-shape.md', anchor: null },
  'decisions/d-27': { file: 'decisions/d-27-pin-the-render-engine.md', anchor: null },

  // toolkit — emails
  'toolkit/emails/invitation': { file: 'toolkit/emails/invitation.md', anchor: null },
  'toolkit/emails/talk-details': { file: 'toolkit/emails/talk-details.md', anchor: null },
  'toolkit/emails/reminder': { file: 'toolkit/emails/reminder.md', anchor: null },
  'toolkit/emails/thank-you': { file: 'toolkit/emails/thank-you.md', anchor: null },
  'toolkit/emails/proposal-received': {
    file: 'toolkit/emails/proposal-received.md',
    anchor: null,
  },
  'toolkit/emails/promotion-starting': {
    file: 'toolkit/emails/promotion-starting.md',
    anchor: null,
  },
  'toolkit/emails/consent-request': { file: 'toolkit/emails/consent-request.md', anchor: null },
  'toolkit/emails/video-online': { file: 'toolkit/emails/video-online.md', anchor: null },
  'toolkit/emails/outreach-sourcing': { file: 'toolkit/emails/outreach-sourcing.md', anchor: null },
  'toolkit/emails/decision-declined': { file: 'toolkit/emails/decision-declined.md', anchor: null },
  'toolkit/emails/decision-parked': { file: 'toolkit/emails/decision-parked.md', anchor: null },
  'toolkit/emails/registration-confirmation': {
    file: 'toolkit/emails/registration-confirmation.md',
    anchor: null,
  },
  // Not "registration-confirmation" above -- that one is the speaker's own
  // announcement e-mail. This is the participant confirmation task 7 sends
  // automatically; kept in the registry for the same reason every other
  // outbound message is, even though nobody opens it from the Templates
  // screen to send it by hand -- see the file's own header note.
  'toolkit/emails/registration-confirmed': {
    file: 'toolkit/emails/registration-confirmed.md',
    anchor: null,
  },
  // Not an e-mail template -- the certificate document itself (phase 4
  // task 12), generated by tools/convener_ops/certificate.py once per eligible
  // attendee and delivered by e-mail (task 14), never committed here. Kept
  // in the registry for the same reason registration-confirmed is above.
  'toolkit/certificate': { file: 'toolkit/certificate.md', anchor: null },
  // The e-mail that carries the certificate above as an attachment (task
  // 14), composed by tools/convener_ops/delivery.py. Same reasoning as
  // registration-confirmed: nobody sends this by hand, kept here so a
  // board member can read the copy without opening the Python module.
  'toolkit/emails/certificate-delivered': {
    file: 'toolkit/emails/certificate-delivered.md',
    anchor: null,
  },
  // The post-event survey's own invitation (phase 4 task 16b), composed
  // by tools/convener_ops/survey_invite.py and sent by an operator dispatching
  // .github/workflows/invite-survey.yml. Same reasoning as
  // certificate-delivered above: nobody sends this by hand, kept here so
  // a board member can read the copy without opening the Python module.
  'toolkit/emails/survey-invitation': {
    file: 'toolkit/emails/survey-invitation.md',
    anchor: null,
  },

  // toolkit — posts
  'toolkit/forum-post-announce': { file: 'toolkit/forum-post-announce.md', anchor: null },
  'toolkit/forum-post-summary': { file: 'toolkit/forum-post-summary.md', anchor: null },
  'toolkit/linkedin-post': { file: 'toolkit/linkedin-post.md', anchor: null },
  'toolkit/mailing-list-announce': {
    file: 'toolkit/mailing-list-announce.md',
    anchor: null,
  },
  'toolkit/recording-announce': { file: 'toolkit/recording-announce.md', anchor: null },
  'toolkit/intro-scripts': { file: 'toolkit/intro-scripts.md', anchor: null },
  'toolkit/run-of-show': { file: 'toolkit/run-of-show.md', anchor: null },
  'toolkit/slides/presentation-template': {
    file: 'toolkit/slides/presentation-template.md',
    anchor: null,
  },
  // toolkit -- visual kit. The page is markdown; the templates it links to are
  // SVG and PNG files under `docs/assets/`, served from the same `handbook/`
  // path by `scripts/copy-handbook.mjs`.
  'toolkit/visual-kit': { file: 'toolkit/visual-kit.md', anchor: null },

  // handbook — long-read
  'handbook/overview': { file: 'start-here/index.md', anchor: null },
  'handbook/glossary': { file: 'start-here/glossary.md', anchor: null },
  'handbook/first-webinar': { file: 'start-here/first-webinar.md', anchor: null },
  'handbook/roles': { file: 'roles.md', anchor: null },
  'handbook/workflow-overview': { file: 'workflow/overview.md', anchor: null },
  'handbook/sourcing': { file: 'workflow/1-sourcing-selection.md', anchor: null },
  'handbook/preparation': { file: 'workflow/2-preparation.md', anchor: null },
  'handbook/hosting': { file: 'workflow/3-hosting.md', anchor: null },
  'handbook/after': { file: 'workflow/4-after.md', anchor: null },
  'handbook/workspace': { file: 'reference/the-workspace.md', anchor: null },
  'handbook/tools': { file: 'reference/tools.md', anchor: null },
  'handbook/contacts': { file: 'reference/contacts.md', anchor: null },
  'handbook/schema': { file: 'reference/schema.md', anchor: null },

  // fragments -- one section of a page, so that a passage two pages need is
  // written on one of them and included by the other. An entry with an anchor
  // is not a second file: it is the same file, scoped to one heading, which is
  // why an included passage cannot hold a version of its own. See
  // `content/transclude.ts`. The keys name their source, so an editor who
  // meets `{{> fragments/roles-no-ladder }}` in a page knows where to go
  // without opening this file.
  'fragments/board-rules-publication-gate': {
    file: 'governance/board-rules.md',
    anchor: 'publishing-a-recording-two-permissions-and-they-are-not-alike',
  },
  'fragments/board-rules-objection': {
    file: 'governance/board-rules.md',
    anchor: 'objecting-and-what-deferral-means',
  },
  'fragments/roles-host-pair': { file: 'roles.md', anchor: 'two-event-hosts-per-webinar' },
  'fragments/roles-no-ladder': { file: 'roles.md', anchor: 'no-ladder-to-climb' },
};

/** Files under `docs/` that ship alongside the content above without ever
 *  being looked up by a content key: the visual kit's two blank templates
 *  and its background image, reached only through a relative link inside
 *  `toolkit/visual-kit.md` (and, for the background, `workflow/3-hosting.md`
 *  too) rather than through `fetchContent`. Kept out of `CONTENT_REGISTRY`
 *  itself so that map keeps meaning exactly "pages the app renders" -- an
 *  SVG run through `substitute` by a test sweeping every registry entry
 *  would be a category error, not a page.
 *
 *  Every entry here was opened and read, not assumed safe from its
 *  extension or its role: the two templates are hand-authored SVG with
 *  `{{speaker.*}}` placeholders and a literal "speaker photo" placeholder
 *  frame, never a real name or a real photograph; the background is a
 *  branded graphic with no person in it. A fourth file, the kit's
 *  "finished example", was on this list until fix round 1 of this task --
 *  it was a real speaker's own photograph and name, kept without a later,
 *  separate consent to use them as a sample (`git log --follow` on
 *  `docs/assets/flyer-example.png` shows this: a pure rename, no content
 *  change, from a filename that named the speaker directly). It is gone
 *  from here and from the page; see `toolkit/visual-kit.md`'s own note on
 *  that slot, and `app/tests/copy-handbook.test.ts`'s regression test
 *  pinning this list to exactly the three that were actually checked.
 *
 *  This list, together with `CONTENT_REGISTRY`'s own file paths, is the
 *  *entire* allowlist `scripts/copy-handbook.mjs` publishes into the app's
 *  built bundle: nothing under `docs/` reaches a reader who is not this
 *  application unless its path is named on one of these two lists. See that
 *  script's own comment, and `app/tests/copy-handbook.test.ts`. */
export const PUBLIC_ASSETS: readonly string[] = [
  'assets/announcement-template.svg',
  'assets/flyer-template.svg',
  'assets/zoom-background.png',
];
