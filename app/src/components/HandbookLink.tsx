type Props = { to: string; children: React.ReactNode };
// `to` is a handbook path like "/workflow/2-preparation/" — now an internal link since app and handbook share the same site.
export function HandbookLink({ to, children }: Props) {
  return (
    <a href={`..${to}`} className="text-xs text-primary underline hover:text-primary-hover">
      {children}
    </a>
  );
}
