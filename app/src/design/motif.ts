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
 * `stroke-accent`, which resolves to `--accent`, the charter's dominant,
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
  family: 'ribbon',
  view_box: '0 0 400 400',
  path:
    'M 42.4 0 C 42.4 42.5 21.2 85 0 85 C -100 93.66 -100 102.33 0 110.99 C 3.54 109.83 14.08 104.38 21.26 104.04 C 28.44 103.71 36.74 105.6 43.07 109 C 49.4 112.4 55.56 118.28 59.25 124.44 C 62.93 130.61 65.2 138.81 65.2 146 C 65.2 153.19 62.93 161.39 59.25 167.56 C 55.56 173.72 49.4 179.6 43.07 183 C 36.74 186.4 28.44 188.29 21.26 187.96 C 14.08 187.62 -11.99 162.54 0 181.01 C 11.99 199.48 81.53 262.3 93.2 298.8 C 104.87 335.3 73.87 383.13 70 400 C 70 1200 1200 1200 1200 1200 C 1200 200 1200 10.61 1200 10.61 C 960 10.61 640 10.61 400 10.61 C 396.48 8.93 386.27 1.69 378.88 0.51 C 371.49 -0.66 362.5 0.51 355.66 3.55 C 348.82 6.59 341.93 12.48 337.85 18.75 C 333.78 25.03 331.2 33.72 331.2 41.2 C 331.2 48.68 333.78 57.37 337.85 63.65 C 341.93 69.92 348.82 75.81 355.66 78.85 C 362.5 81.89 371.49 83.06 378.88 81.89 C 386.27 80.71 395.28 72.14 400 71.79 C 404.72 71.44 407.2 76.46 407.2 79.79 C 407.2 83.12 404.33 78.95 400 91.79 C 395.67 104.62 381.2 140.43 381.2 156.8 C 381.2 173.17 396.87 184.47 400 190',
  stroke_width: '9.6',
};
