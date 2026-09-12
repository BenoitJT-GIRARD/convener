/**
 * The motif the cockpit's chrome draws.
 *
 * Generated, not authored: `tools/scripts/generate_motif.py` writes this
 * file from the family the charter in force names, through
 * `tools/convener_ops/publication/motifs/`. The showcase reads the same
 * drawing from `site/src/_data/motif.json`, written by the same run. Edit
 * the charter, not this file.
 *
 * The geometry is never derived here. `auth/Login.tsx` interpolates the
 * values below into an `<svg>`; the path and the weight were computed by
 * the family itself, on the square canvas `generate_motif.py::CANVAS`
 * names -- D-14's boundary, which is the fixture rather than the code
 * that produces it.
 *
 * The colour is not here either. The stroke is Tailwind's
 * `stroke-dominant`, which resolves to `--dominant`, the charter's dominant,
 * generated into `design/tokens.css` by `generate_brand_css.py`.
 *
 * `snake_case` keys: they are `site/src/_data/motif.json`'s own, and one
 * drawing spelled two ways across the boundary is what this file exists
 * to stop.
 */
export interface Motif {
  /** The family a charter's `motif.family` names. */
  family: string;
  /** The square the drawing was computed on. */
  view_box: string;
  /** The `d` attribute, whole. */
  path: string;
  /** The `stroke-width`, in the canvas's own units. */
  stroke_width: string;
}

export const MOTIF: Motif = {
  family: 'bracket',
  view_box: '0 0 400 400',
  path:
    'M 56.12 105.13 L 56.12 68 L 7.32 68 L 7.32 183.2 L 56.12 183.2 L 56.12 146.07 M 364.06 33.78 L 364.06 10 L 395.31 10 L 395.31 83.78 L 364.06 83.78 L 364.06 60',
  stroke_width: '8.16',
};
