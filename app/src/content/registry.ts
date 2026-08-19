export interface ContentEntry {
  /** path under `docs/` in the repo */
  file: string;
  /** optional heading anchor (slug from `## Heading`) to scope the render */
  anchor: string | null;
}

export const CONTENT_REGISTRY: Record<string, ContentEntry> = {
  // governance
  'governance/selection-criteria': { file: 'governance/selection-criteria.md', anchor: null },
  'governance/editorial-line': { file: 'governance/editorial-line.md', anchor: null },
  'governance/editorial-board': { file: 'governance/editorial-board.md', anchor: null },
  'governance/board-rules': { file: 'governance/board-rules.md', anchor: null },
  'governance/conflict-of-interest': { file: 'governance/conflict-of-interest.md', anchor: null },
  'governance/decisions': { file: 'governance/decisions.md', anchor: null },

  // toolkit — emails
  'toolkit/emails/invitation': { file: 'toolkit/emails/invitation.md', anchor: null },
  'toolkit/emails/talk-details': { file: 'toolkit/emails/talk-details.md', anchor: null },
  'toolkit/emails/zoom-request': { file: 'toolkit/emails/zoom-request.md', anchor: null },
  'toolkit/emails/reminder': { file: 'toolkit/emails/reminder.md', anchor: null },
  'toolkit/emails/thank-you': { file: 'toolkit/emails/thank-you.md', anchor: null },
  'toolkit/emails/consent-request': { file: 'toolkit/emails/consent-request.md', anchor: null },
  'toolkit/emails/outreach-sourcing': { file: 'toolkit/emails/outreach-sourcing.md', anchor: null },
  'toolkit/emails/decision-declined': { file: 'toolkit/emails/decision-declined.md', anchor: null },
  'toolkit/emails/decision-parked': { file: 'toolkit/emails/decision-parked.md', anchor: null },
  'toolkit/emails/registration-confirmation': {
    file: 'toolkit/emails/registration-confirmation.md',
    anchor: null,
  },

  // toolkit — posts
  'toolkit/forum-post-announce': { file: 'toolkit/forum-post-announce.md', anchor: null },
  'toolkit/forum-post-summary': { file: 'toolkit/forum-post-summary.md', anchor: null },
  'toolkit/linkedin-post': { file: 'toolkit/linkedin-post.md', anchor: null },
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
  'handbook/tools': { file: 'reference/tools.md', anchor: null },
  'handbook/contacts': { file: 'reference/contacts.md', anchor: null },
  'handbook/schema': { file: 'reference/schema.md', anchor: null },
};
