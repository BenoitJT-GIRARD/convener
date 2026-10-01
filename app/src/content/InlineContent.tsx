import { lazy, Suspense, useEffect, useState } from 'react';
import { fetchContent, editUrlFor } from './fetch';
import { substitute, substituteWithoutSpeaker, type SubstitutionContext } from './render';
import { useAuth } from '../auth/AuthContext';
import { isDemoMode } from '../data/demo';

/**
 * The markdown renderer, fetched when a screen actually renders content.
 *
 * `react-markdown` and `remark-gfm` are seventy-one packages of the unified
 * pipeline and weigh 45,808 B gzip -- 21% of this bundle, measured. Most
 * screens a volunteer opens render no handbook content: the pipeline, the
 * agenda, the board, the settings. They were all paying for a markdown
 * renderer on arrival.
 *
 * It must stay a dynamic import. A static one would put the pipeline back in
 * the entry chunk and nothing on screen would change, so
 * `app/tests/content/markdown-is-loaded-when-it-is-needed.test.ts` reads for
 * it; `src/content/Markdown.tsx` carries the rest of the argument.
 */
const Markdown = lazy(() => import('./Markdown'));

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
        {/* The same wording the fetch above shows, because to a volunteer it
            is the same wait: the text is on its way, or the renderer is, and
            which of the two is not a distinction worth a second sentence. */}
        <Suspense fallback={<p className="text-ink-muted text-sm">Loading content…</p>}>
          <Markdown text={rendered} contentKey={contentKey} variant={variant} />
        </Suspense>
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
