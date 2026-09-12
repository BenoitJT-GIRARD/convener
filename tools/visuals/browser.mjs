/* The one place this repository launches a browser, and the whole of the
 * argument for the one flag it sometimes passes.
 *
 * Five scripts in this package open a page and take a picture of it, and
 * a sixth (`site/scripts/check-a11y.mjs`) sweeps a built showcase with
 * axe-core. Before this file existed each of them called
 * `puppeteer.launch({ headless: true })` for itself, which was fine for
 * as long as the only machine that ever ran them was the maintainer's.
 * The first run on Linux killed five of the six at once:
 *
 *   FATAL:content/browser/zygote_host/zygote_host_impl_linux.cc:129]
 *   No usable sandbox!
 *
 * The obliging repair is `--no-sandbox` typed into five files. What that
 * costs is five places where a reader finds a disabled security boundary
 * with no argument beside it, and five places to correct when the
 * argument stops being true. So the flag is stated here once, with its
 * reasons, and the scripts call `launch` instead.
 *
 * Why the sandbox has to go at all
 * --------------------------------
 * Chrome's renderer sandbox needs an unprivileged user namespace. Ubuntu
 * 24.04 -- which is what `ubuntu-latest` is -- restricts those through
 * AppArmor, and grants them back through a per-binary profile shipped
 * with a packaged browser. A browser `puppeteer` downloads for itself
 * lands under `~/.cache/puppeteer/chrome/`, in a directory named for the
 * build it fetched, which no profile names -- so its zygote cannot build
 * a namespace and Chrome aborts before it opens a page. Nothing in the
 * launch is wrong; the binary is simply somewhere AppArmor does not
 * recognise.
 *
 * Why waiving it is acceptable *here*
 * -----------------------------------
 * The sandbox exists to contain a page that the person running the
 * browser did not write. Not one of the six callers opens such a page.
 * Every one of them serves a directory this repository just built, over
 * a loopback address, on an ephemeral port, to a browser that lives as
 * long as the script does; the renderers are shown this repository's own
 * HTML, its own CSS and its own fonts, and no navigation reaches the
 * network. On a throw-away runner the process the sandbox would have
 * confined and the process it would have protected are the same job,
 * checked out from the same commit. There is no untrusted content on
 * either side of the boundary, which is the condition under which
 * removing it costs nothing.
 *
 * That argument does not extend one inch further. It would stop being
 * true the moment one of these scripts was pointed at a URL somebody
 * else controls, and the right repair then is to put the sandbox back,
 * not to widen this comment.
 *
 * Where it is waived, and where it deliberately is not
 * ----------------------------------------------------
 * Two narrowings, both measured rather than assumed:
 *
 * 1. *Only on Linux.* Windows and macOS put no AppArmor policy in front
 *    of a downloaded Chrome, their sandboxes start, and a flag passed
 *    there would disable a boundary that was working. The maintainer's
 *    own machine is Windows, so this is also the platform the checks are
 *    developed on: it keeps its sandbox.
 *
 * 2. *Only for a browser this repository downloaded itself.* A caller
 *    that passes `executablePath` is naming a browser the machine
 *    already had -- `site/scripts/check-a11y.mjs` is handed
 *    `/usr/bin/google-chrome-stable`, which `ubuntu-latest` ships
 *    preinstalled -- and a packaged browser arrives with the AppArmor
 *    profile that grants it the namespace. It does not need the flag and
 *    does not get it. That is not a guess: on the run that killed the
 *    five scripts above, the accessibility job rendered 38
 *    page-viewport combinations through that binary and passed, with its
 *    sandbox intact.
 *
 *    The second rule is therefore about provenance and not about
 *    spelling. A caller that ever sets `executablePath` to a
 *    Chrome-for-Testing binary this repository fetched would be handed no
 *    flag and would fail the way the five did -- and this file is the one
 *    place to teach that case, rather than anywhere it is launched from.
 *
 * `tools/tests/repository/test_browser_launch.py` holds both halves: that
 * every launch in this repository comes through here, and that this is
 * the only file in it that names the flag.
 */

/** The flag itself, named once so that a search for it lands here. */
export const NO_SANDBOX = '--no-sandbox';

/**
 * Whether a launch described by `options` runs a browser whose sandbox
 * cannot start. See this module's own comment for both conditions and
 * the measurement behind each.
 *
 * @param {{ executablePath?: string }} options the launch options a
 *   caller is about to use.
 * @returns {boolean}
 */
export function sandboxIsUnavailable(options = {}) {
  return process.platform === 'linux' && !options.executablePath;
}

/**
 * Launch a browser the way this repository launches browsers.
 *
 * `puppeteer` is passed in rather than imported: this package depends on
 * the full `puppeteer` and `site/` on `puppeteer-core`, and
 * `render-readme-shots.mjs` imports its copy lazily so that the script
 * can refuse a bad invocation on a machine that never installed one. A
 * module that imported either would take that choice away from all three.
 *
 * @param {{ launch: (options: object) => Promise<object> }} puppeteer the
 *   caller's own puppeteer module.
 * @param {object} [options] anything puppeteer takes. `headless` defaults
 *   to true, and `args` is appended to rather than replaced.
 * @returns {Promise<object>} the launched browser.
 */
export async function launch(puppeteer, options = {}) {
  const { args = [], ...rest } = options;
  return puppeteer.launch({
    headless: true,
    ...rest,
    args: sandboxIsUnavailable(options) ? [...args, NO_SANDBOX] : [...args],
  });
}
