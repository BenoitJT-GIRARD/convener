import { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { fetchContent } from './fetch';
import { substitute, type SubstitutionContext } from './render';
import { useAuth } from '../auth/AuthContext';

interface Props {
  contentKey: string;
  ctx?: SubstitutionContext;
  variant?: 'inline' | 'page';
}

export function InlineContent({ contentKey, ctx, variant = 'inline' }: Props) {
  const { token } = useAuth();
  const [text, setText] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setText(null);
    setErr(null);
    fetchContent(contentKey, token)
      .then(setText)
      .catch(e => setErr(e.message));
  }, [contentKey, token]);

  if (err) return <p className="text-danger text-sm">{err}</p>;
  if (text === null) return <p className="text-ink-muted text-sm">Loading content…</p>;

  const rendered = ctx ? substitute(text, ctx) : text;
  const wrapperCls =
    variant === 'page'
      ? 'prose max-w-none text-sm'
      : 'prose prose-sm max-w-none bg-paper border border-border rounded p-4 text-sm';

  return (
    <div className={wrapperCls}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{rendered}</ReactMarkdown>
      {variant === 'inline' && (
        <div className="mt-3 text-right">
          <button
            onClick={() => navigator.clipboard.writeText(rendered)}
            className="text-xs text-primary underline"
          >
            Copy to clipboard
          </button>
        </div>
      )}
    </div>
  );
}
