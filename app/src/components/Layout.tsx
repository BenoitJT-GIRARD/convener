import { Outlet, Link } from 'react-router-dom';
import { TopTabs } from './TopTabs';
import { useAuth } from '../auth/AuthContext';
import { useRole } from '../auth/useRole';
import { useData } from '../data/DataContext';
import { isDemoMode, exitDemoMode } from '../data/demo';
import { instanceIdentity } from '../instance';
import { dataDir, speakersFile } from '../paths';
import { productNotice } from '../notice';
import { UnconfiguredBanner } from './UnconfiguredBanner';

function exitDemo() {
  exitDemoMode();
  window.location.reload();
}

export function Layout() {
  const instance = instanceIdentity();
  const notice = productNotice();
  const demo = isDemoMode();
  const { login, signOut } = useAuth();
  const role = useRole();
  const { saveError, clearSaveError } = useData();
  return (
    <>
      {/* Above the masthead, not below it: the masthead is the thing
          that is wrong -- it names whoever the declaration says runs
          this series, and on an unconfigured duplicate that is the
          example collective. See UnconfiguredBanner's own header. */}
      <UnconfiguredBanner />
      <header className="bg-primary text-white border-b-4 border-accent">
        <div className="max-w-content mx-auto px-6 py-3 flex items-center justify-between gap-4 flex-wrap">
          <Link to="/" className="flex items-baseline gap-2 no-underline">
            <span className="font-mono text-sm opacity-85">No.</span>
            <span className="font-display font-extrabold tracking-wider uppercase text-sm">
              {instance.organisation}
            </span>
            <span className="font-display font-medium text-sm opacity-90 tracking-wide">
              {instance.series}
            </span>
            <span className="ml-2 px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-wider bg-accent/40 border border-white/30">
              Organiser
            </span>
          </Link>
          <div className="flex items-center gap-3 text-sm">
            {login && (
              <span className="font-mono text-xs opacity-85">
                {login}{role && ` · ${role}`}
              </span>
            )}
            <button
              onClick={signOut}
              className="font-display font-bold text-[11px] tracking-widest uppercase border border-white/45 px-3 py-1.5 hover:bg-white/15 transition-colors"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      {demo && (
        <div className="bg-accent text-white text-sm py-2 px-6">
          <div className="max-w-content mx-auto flex items-center justify-between flex-wrap gap-2">
            <span>
              <strong className="font-display tracking-wide uppercase text-xs mr-2">Demo</strong>
              {/* Which invented records these are, not just that they are
                  invented: the masthead above names whoever runs this
                  cockpit, while every record on screen belongs to the
                  example instance this product ships (`instances/example/`,
                  read by `data/demo.ts`). Saying "data is mocked" left a
                  visitor to guess why the two disagree. */}
              These are the example instance&rsquo;s records, not this series&rsquo;.
              Edits stay in this tab and are never saved.
            </span>
            <button
              onClick={exitDemo}
              className="font-display font-bold text-[11px] tracking-widest uppercase underline underline-offset-2"
            >
              Exit demo
            </button>
          </div>
        </div>
      )}

      {saveError && (
        <div className="bg-danger/10 border-b-2 border-danger text-danger text-sm py-2 px-6">
          <div className="max-w-content mx-auto flex items-center justify-between flex-wrap gap-2">
            <span>{saveError}</span>
            <button
              onClick={clearSaveError}
              className="font-display font-bold text-[11px] tracking-widest uppercase underline underline-offset-2"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      <div className="max-w-content mx-auto px-6 py-8">
        <TopTabs />
        <main>
          <Outlet />
        </main>
      </div>

      <footer className="border-t border-border mt-16">
        <div className="max-w-content mx-auto px-6 py-6 flex items-center justify-between text-xs text-ink-muted flex-wrap gap-2">
          <p>
            {/* Where the records on screen actually come from. In demo mode
                that is not this repository's own `instance/data/`: it is the example
                instance the product ships, and saying otherwise would send
                a curious visitor to look for these five people in a file
                that has never held them. */}
            <em>Operational workspace</em> &middot; data lives in{' '}
            <code className="text-ink">
              {demo ? `instances/example/${dataDir()}` : speakersFile()}
            </code>
          </p>
          <a
            href={instance.forum}
            className="font-mono text-[11px] tracking-wider uppercase hover:text-accent"
          >
            {instance.forum_host} →
          </a>
        </div>
        {/* The product's own Appropriate Legal Notice, in the sense section 0
            of the licence gives that phrase: whose work this is, that a
            licensee may convey it and under what, that there is no warranty,
            and where to read the licence. Section 5 is why it is worth
            displaying rather than merely shipping -- an interface that
            displays one obliges every modified version's interface to
            display one too. A line saying only who wrote this would oblige
            nobody.

            Below the line that names this instance, and separated from it by
            a rule, because the two say different kinds of thing: everything
            above comes from `instance/config.json` and belongs to whoever
            runs this cockpit, and nothing here does. `NOTICE.json` is the one
            declaration, read by `scripts/notice.mjs` and carried into this
            bundle by `vite.config.ts`'s own define -- see `src/notice.ts`. */}
        <div className="max-w-content mx-auto px-6 pb-6 pt-4 border-t border-border text-xs text-ink-muted">
          <p>
            <span className="font-display font-bold tracking-wide">{notice.product}</span>
            {' · '}
            {notice.copyright}. {notice.terms} {notice.warranty}{' '}
            <a
              href={notice.licence_url}
              rel="license"
              className="underline underline-offset-2 hover:text-accent"
            >
              {notice.licence_name}
            </a>
          </p>
        </div>
      </footer>
    </>
  );
}
