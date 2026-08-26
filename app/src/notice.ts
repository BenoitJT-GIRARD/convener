/**
 * What this product says about itself, on the application's side of the
 * language boundary.
 *
 * One declaration -- `NOTICE.json` at the repository root -- and one reader
 * per language: `app/scripts/notice.mjs` for this build,
 * `site/scripts/notice.cjs` for the showcase's. This module is not a third
 * reader: it is how the value that build already read reaches the browser,
 * where no file can be read at all. `vite.config.ts` substitutes the whole
 * object into every bundle through Vite's own `define`, exactly as it
 * already does for the instance's identity.
 *
 * **This is the product's, and that is the point of it being separate from
 * `instance.ts`.** The identity next door says who is running this cockpit
 * and a duplicate edits it before its first build. Nothing here is a
 * duplicate's to edit: it names the software, its author, its licence and
 * the absence of a warranty, and it says the same thing in every instance
 * ever derived from this repository. A notice that an instance could
 * configure would be a notice a modified version could quietly empty, which
 * is the failure section 5 of the licence exists to prevent.
 *
 * Throws rather than defaulting, the same rule `instance.ts` follows. A
 * bundle built without the define displays no notice, and a page displaying
 * no notice is indistinguishable from a page whose notice was removed on
 * purpose (D-25).
 */

/** The vocabulary, and the whole of it. Mirrors `NOTICE.json`'s own keys and
 *  `scripts/notice.mjs::FIELDS`; `snake_case` because these keys are the
 *  declaration's own, and renaming them on the way in would be a second
 *  spelling of each. */
export interface ProductNotice {
  /** The software's name -- what a fork renames, and the only field of this
   *  notice a fork may change (TRADEMARK.md). */
  product: string;
  /** The copyright notice section 0 of the licence asks for. */
  copyright: string;
  /** That a licensee may convey the work, and under what. */
  terms: string;
  /** That there is none. */
  warranty: string;
  /** How to read a copy of the licence: the name of the link, and where it
   *  goes. Not a path inside this repository -- the showcase is published as
   *  a static build that carries no `LICENSE` file, so a relative link would
   *  answer "how do I read the licence" with a missing page. */
  licence_name: string;
  licence_url: string;
}

let cached: ProductNotice | null = null;

/** The product's own Appropriate Legal Notice, parsed once. */
export function productNotice(): ProductNotice {
  if (cached) return cached;
  const raw = import.meta.env.VITE_PRODUCT_NOTICE as string | undefined;
  if (!raw) {
    throw new Error(
      'VITE_PRODUCT_NOTICE is unset: this bundle was built without ' +
        "vite.config.ts's own define, so it can display no Appropriate Legal " +
        'Notice at all (see NOTICE.json)',
    );
  }
  cached = JSON.parse(raw) as ProductNotice;
  return cached;
}
