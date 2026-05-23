import { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { fetchContent, editUrlFor } from './fetch';
import { substitute, type SubstitutionContext } from './render';
import { useAuth } from '../auth/AuthContext';
import { isDemoMode } from '../data/demo';

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

  useEffect(() => {
    setText(null);
    setErr(null);
    setCopied(false);
    fetchContent(contentKey, token)
      .then(setText)
      .catch(e => setErr(e.message));
  }, [contentKey, token]);

  if (err) return <p className="text-danger text-sm">{err}</p>;
  if (text === null) return <p className="text-ink-muted text-sm">Loading content…</p>;

  const rendered = ctx ? substitute(text, ctx) : text;
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
            className="font-display font-bold text-[11px] tracking-widest uppercase text-ink-muted hover:text-accent border border-border px-2.5 py-1 hover:border-accent transition-colors no-underline"
          >
            ✎ Edit on GitHub
          </a>
        </div>
      )}
      <div className={wrapperCls}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{rendered}</ReactMarkdown>
      </div>
      {variant === 'inline' && (
        <div className="mt-2 flex justify-end gap-2">
          {showEdit && (
            <a
              href={editUrl!}
              target="_blank"
              rel="noreferrer"
              title="Open this file in the GitHub web editor"
              className="font-display font-bold text-[11px] tracking-widest uppercase text-ink-muted hover:text-accent border border-border px-2.5 py-1 hover:border-accent transition-colors no-underline"
            >
              ✎ Edit
            </a>
          )}
          <button
            onClick={copy}
            className="font-display font-bold text-[11px] tracking-widest uppercase text-primary-hover border border-border px-2.5 py-1 hover:bg-primary-soft transition-colors"
          >
            {copied ? '✓ Copied' : 'Copy to clipboard'}
          </button>
        </div>
      )}
    </div>
  );
}
