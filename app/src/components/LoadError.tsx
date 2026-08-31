import { useData } from '../data/DataContext';

/** Shown full-screen in place of a screen's content when the initial data
 *  load (or an explicit reload) fails -- there is genuinely nothing to
 *  render in that case. `error` is already a plain-language sentence (see
 *  src/github/errors.ts); a save failure never reaches here, see
 *  DataContext's `saveError` and the dismissible banner in Layout. */
export function LoadError({ message }: { message: string }) {
  const { reload } = useData();
  return (
    <div className="space-y-4">
      <p className="text-danger">{message}</p>
      <button
        type="button"
        onClick={reload}
        className="font-display font-bold tracking-widest uppercase text-sm bg-dominant text-white border-2 border-dominant px-6 py-3 hover:bg-dominant-hover hover:border-dominant-hover transition-colors"
      >
        Try again
      </button>
    </div>
  );
}
