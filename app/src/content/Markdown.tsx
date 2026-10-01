import { Children, isValidElement } from 'react';
import type { ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { handbookUrl } from './fetch';
import { slugify } from './transclude';

/**
 * The markdown renderer, in a module of its own so it can be fetched when a
 * screen actually renders handbook content.
 *
 * **Why it is split out, measured.** `react-markdown` and `remark-gfm` bring
 * seventy-one packages of the unified pipeline, and in this bundle they weigh
 * **45,808 B gzip — 21% of it**. One file imported them, and most screens a
 * volunteer opens render no handbook content at all: the pipeline, the
 * agenda, the board, the settings. Every one of those was paying for a
 * markdown renderer on arrival.
 *
 * `site/scripts/check-performance-budget.mjs` weighs the cockpit's document
 * plus every resource that document asks for, which is what a volunteer
 * downloads before anything is on screen. A chunk fetched by the application
 * at the moment it is needed is not one of those. The honest statement of
 * what this buys: the *first* load drops by those 45 KB; somebody who opens a
 * content screen downloads the same bytes, in two steps.
 *
 * **It made two readings wait longer, and the first diagnosis of that was
 * wrong.** `visual-kit.test.tsx`'s flyer link and
 * `consent-request.test.tsx`'s message stopped finding what they render.
 * React had just gone 19.2.8 to 19.3.0 in the same batch, and holding that
 * version made them pass -- which looked like the answer and was not: run on
 * their own they pass on both versions, and run inside the full suite they
 * failed on both. Rendering content is simply two awaits deep now, the text
 * and then the renderer, and testing-library's one-second window is a window
 * this suite's own load decides. `tests/helpers/setup.ts` carries the
 * measurement and the setting.
 *
 * **Nothing here may be imported by `InlineContent`.** That is the whole
 * point of the split, and a static import would quietly undo it --
 * `app/tests/content/markdown-is-loaded-when-it-is-needed.test.ts` reads for
 * exactly that.
 */

/** The text of a heading, whatever react-markdown made of its inline
 *  markup -- a heading may hold emphasis or code, and the anchor is
 *  computed from the words rather than from the nodes. */
function headingText(children: ReactNode): string {
  return Children.toArray(children)
    .map(child => {
      if (typeof child === 'string' || typeof child === 'number') return String(child);
      if (isValidElement<{ children?: ReactNode }>(child)) {
        return headingText(child.props.children);
      }
      return '';
    })
    .join('');
}

/**
 * Every heading of a rendered page carries the anchor its own prose
 * already links to.
 *
 * `transclude.ts::slugify` is GitHub's rule, and it is the rule the
 * registry's own fragments are declared under, so a heading is reachable
 * by the same name from a link, from an include and from this. Without
 * these, `#/handbook/toolkit/run-of-show#results-that-have-not-been-peer-
 * reviewed` would open the right page at the top of it.
 *
 * Page renders only: an inline render is a fragment dropped into a
 * screen that already has headings of its own, and several of them can
 * sit on one screen, so ids there would be duplicates rather than
 * anchors.
 */
const HEADING_ANCHORS: Components = {
  h1: ({ children }) => <h1 id={slugify(headingText(children))}>{children}</h1>,
  h2: ({ children }) => <h2 id={slugify(headingText(children))}>{children}</h2>,
  h3: ({ children }) => <h3 id={slugify(headingText(children))}>{children}</h3>,
  h4: ({ children }) => <h4 id={slugify(headingText(children))}>{children}</h4>,
};

interface Props {
  /** The markdown to render, substitutions already applied. */
  text: string;
  /** The content key the text was fetched under. `handbookUrl` resolves a
   *  link written inside the markdown against the `docs/` path it came from,
   *  so a relative link in the handbook is the same link in the app. */
  contentKey: string;
  variant: 'inline' | 'page';
}

/** A default export, because `React.lazy` takes a module whose default is the
 *  component. */
export default function Markdown({ text, contentKey, variant }: Props) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      urlTransform={href => handbookUrl(contentKey, href)}
      components={variant === 'page' ? HEADING_ANCHORS : undefined}
    >
      {text}
    </ReactMarkdown>
  );
}
