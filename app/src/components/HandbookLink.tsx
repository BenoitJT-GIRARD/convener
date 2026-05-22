type Props = { to: string; children: React.ReactNode };
// `to` is a handbook path like "/workflow/2-preparation/" (handbook is served at the site root, the app at /app/)
export function HandbookLink({ to, children }: Props) {
  return (
    <a href={`..${to}`} className="text-xs text-ink-muted hover:text-primary inline-flex items-center gap-1">
      ↗ <span className="underline">{children}</span>
    </a>
  );
}
