import { Children, isValidElement, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { fetchContent, editUrlFor, handbookUrl } from './fetch';
import { slugify } from './transclude';
import { substitute, substituteWithoutSpeaker, type SubstitutionContext } from './render';
import { useAuth } from '../auth/AuthContext';
import { isDemoMode } from '../data/demo';

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
  contentKey: string;
  ctx?: SubstitutionContext;
  variant?: 'inline' | 'page';
}

export function InlineContent({ contentKey, ctx, variant = 'inline' }: Props) {
  const { token } = useAuth();
  const [text, setText] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // When the request identity (contentKey/token) changes, reset the display
  // state during render rather than from inside the effect below — this is
  // React's documented pattern for "adjusting state when a prop changes"
  // (react.dev), and keeps the effect itself free of synchronous setState.
  const requestKey = `${contentKey}::${token ?? ''}`;
  const [loadedFor, setLoadedFor] = useState(requestKey);
  if (loadedFor !== requestKey) {
    setLoadedFor(requestKey);
    setText(null);
    setErr(null);
    setCopied(false);
  }

  useEffect(() => {
    fetchContent(contentKey, token)
      .then(setText)
      .catch(e => setErr(e.message));
  }, [contentKey, token]);

  if (err) return <p className="text-danger text-sm">{err}</p>;
  if (text === null) return <p className="text-ink-muted text-sm">Loading content…</p>;

  const rendered = ctx ? substitute(text, ctx) : substituteWithoutSpeaker(text);
  const wrapperCls = variant === 'page' ? 'prose prose-page' : 'prose prose-inline';
  const editUrl = editUrlFor(contentKey);
  const showEdit = !!editUrl && !isDemoMode();

  async function copy() {
    try {
      await navigator.clipboard.writeText(rendered);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* ignore */
    }
  }

  return (
    <div>
      {variant === 'page' && showEdit && (
        <div className="flex justify-end mb-2">
          <a
            href={editUrl!}
            target="_blank"
            rel="noreferrer"
            title="Open this file in the GitHub web editor"
            className="font-display font-bold text-[11px] tracking-widest uppercase text-ink-muted hover:text-dominant border border-border px-2.5 py-1 hover:border-dominant transition-colors no-underline"
          >
            ✎ Edit on GitHub
          </a>
        </div>
      )}
      <div className={wrapperCls}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          urlTransform={href => handbookUrl(contentKey, href)}
          components={variant === 'page' ? HEADING_ANCHORS : undefined}
        >
          {rendered}
        </ReactMarkdown>
      </div>
      {variant === 'inline' && (
        <div className="mt-2 flex justify-end gap-2">
          {showEdit && (
            <a
              href={editUrl!}
              target="_blank"
              rel="noreferrer"
              title="Open this file in the GitHub web editor"
              className="font-display font-bold text-[11px] tracking-widest uppercase text-ink-muted hover:text-dominant border border-border px-2.5 py-1 hover:border-dominant transition-colors no-underline"
            >
              ✎ Edit
            </a>
          )}
          <button
            onClick={copy}
            className="font-display font-bold text-[11px] tracking-widest uppercase text-field-text border border-border px-2.5 py-1 hover:bg-paper-soft transition-colors"
          >
            {copied ? '✓ Copied' : 'Copy to clipboard'}
          </button>
        </div>
      )}
    </div>
  );
}
