import { useState } from 'react';
import type { ReactNode } from 'react';
import { useAuth } from './AuthContext';
import { activateDemoMode } from '../data/demo';
import { authEnv, availableStrategy } from './strategy';
import { requestDeviceCode, pollForToken, DeviceFlowError } from './device';
import type { DeviceCode } from './device';
import { instanceIdentity } from '../instance';
import { UnconfiguredBanner } from '../components/UnconfiguredBanner';

function realSleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function Shell({ children }: { children: ReactNode }) {
  const instance = instanceIdentity();
  function enterDemo() {
    activateDemoMode();
    window.location.reload();
  }

  return (
    <div className="min-h-screen relative overflow-hidden">
      <svg
        aria-hidden="true"
        viewBox="0 0 400 400"
        /* stroke-accent, not a hex literal: --accent is instance/data/brand.json's
           purple, generated into tokens.css by generate_brand_css.py. */
        className="absolute -right-20 top-10 w-[420px] max-w-[55vw] pointer-events-none opacity-90 stroke-accent"
        fill="none"
        strokeWidth="9"
        strokeLinecap="round"
      >
        <path d="M 320 60 C 380 60 400 130 340 150 C 280 170 270 90 330 90 C 380 90 370 180 300 200" opacity=".85" />
        <path d="M 250 230 C 320 220 360 290 290 310 C 230 326 220 250 280 250 C 340 250 330 350 250 350" opacity=".9" />
        <path d="M 70 270 C 30 290 50 360 110 350 C 160 342 160 280 120 280 C 80 280 60 340 120 360" opacity=".7" />
      </svg>

      {/* The one screen of this bundle a visitor with no account
          actually reaches, so the one place the warning is addressed to
          somebody other than the operator who already knows. */}
      <div className="relative z-10">
        <UnconfiguredBanner />
      </div>
      <header className="bg-primary text-white border-b-4 border-accent relative z-10">
        <div className="max-w-content mx-auto px-6 py-3 flex items-baseline gap-2">
          <span className="font-mono text-sm opacity-85">No.</span>
          <span className="font-display font-extrabold tracking-wider uppercase text-sm">
            {instance.organisation}
          </span>
          <span className="font-display font-medium text-sm opacity-90 tracking-wide">
            {instance.series}
          </span>
          <span className="ml-2 px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-wider bg-accent/40 border border-white/30">
            Organizer
          </span>
        </div>
      </header>

      <div className="max-w-md mx-auto px-6 py-20 relative z-10">
        <p className="text-xs font-bold tracking-[0.14em] uppercase text-accent mb-3 flex items-center gap-3">
          <span className="h-0.5 bg-accent w-8" />
          Sign in
        </p>
        <h1 className="font-display font-extrabold text-4xl uppercase tracking-tight mb-4 leading-[1.05]">
          For the team.
        </h1>

        {children}

        <div className="mt-12 pt-8 border-t border-border">
          <p className="text-xs font-bold tracking-[0.14em] uppercase text-ink-muted mb-2">
            Just exploring?
          </p>
          <button
            type="button"
            onClick={enterDemo}
            className="font-display font-bold tracking-wider uppercase text-sm text-accent border-2 border-accent px-5 py-2.5 hover:bg-accent hover:text-white transition-colors"
          >
            View a live demo
          </button>
          <p className="text-xs text-ink-muted mt-3">
            No sign-in required, edits stay local to your browser tab.
          </p>
        </div>
      </div>
    </div>
  );
}

function TokenPanel() {
  const [owner, repository] = instanceIdentity().repository.split('/');
  const { signIn } = useAuth();
  const [token, setToken] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    const ok = await signIn(token.trim());
    setBusy(false);
    if (!ok) {
      setErr(
        'That did not work. Check the token and your internet connection, then try again.',
      );
    }
  }

  return (
    <>
      <p className="text-ink-muted mb-8 max-w-prose">
        Sign-in with a short code is not configured yet, so this instance uses a personal
        access token. You need a fine-grained personal access token with read/write access
        to the <code className="font-mono text-ink">{repository}</code> repository.
      </p>

      <details className="mb-8 text-sm border-l-2 border-primary pl-4">
        <summary className="cursor-pointer font-display font-bold uppercase tracking-wider text-xs text-primary-hover">
          How to generate a token (one minute)
        </summary>
        <ol className="list-decimal pl-6 mt-3 space-y-1.5 text-ink-muted">
          <li>
            Open{' '}
            <a
              className="underline"
              href="https://github.com/settings/personal-access-tokens/new"
              target="_blank"
              rel="noreferrer"
            >
              github.com/settings/personal-access-tokens/new
            </a>
            .
          </li>
          <li>
            Resource owner: <code className="font-mono text-ink">{owner}</code>. Repository
            access: only <code className="font-mono text-ink">{repository}</code>.
          </li>
          <li>
            Permissions: <em>Contents: read &amp; write</em>, <em>Issues: read &amp; write</em>.
          </li>
          <li>Generate, copy the token, paste below.</li>
        </ol>
      </details>

      <form onSubmit={submit} className="space-y-4">
        <input
          type="password"
          placeholder="github_pat_..."
          value={token}
          onChange={e => setToken(e.target.value)}
          className="w-full px-3 py-3 font-mono text-sm"
          required
        />
        <button
          type="submit"
          disabled={busy}
          className="font-display font-bold tracking-widest uppercase text-sm bg-primary text-white border-2 border-primary px-6 py-3 hover:bg-primary-hover hover:border-primary-hover disabled:opacity-50 transition-colors"
        >
          {busy ? 'Checking...' : 'Sign in ->'}
        </button>
        {err && <p className="text-danger text-sm">{err}</p>}
      </form>
    </>
  );
}

type DeviceState =
  | { step: 'idle' }
  | { step: 'requesting' }
  | { step: 'code'; code: DeviceCode }
  | { step: 'error'; message: string };

function DevicePanel({ proxyUrl, clientId }: { proxyUrl: string; clientId: string }) {
  const { signInWithTokens } = useAuth();
  const [state, setState] = useState<DeviceState>({ step: 'idle' });

  async function start() {
    setState({ step: 'requesting' });
    try {
      const code = await requestDeviceCode(proxyUrl, clientId);
      setState({ step: 'code', code });
      const tokens = await pollForToken(proxyUrl, clientId, code.device_code, {
        interval: code.interval,
        sleep: realSleep,
      });
      const ok = await signInWithTokens(tokens.access_token);
      if (!ok) {
        setState({
          step: 'error',
          message: 'Sign-in succeeded on GitHub, but the token was rejected. Please try again.',
        });
      }
    } catch (e) {
      const message = e instanceof DeviceFlowError ? e.message : 'Sign-in failed. Please try again.';
      setState({ step: 'error', message });
    }
  }

  if (state.step === 'code') {
    return (
      <div className="space-y-5">
        <p className="text-ink-muted max-w-prose">
          Open GitHub and enter this code to finish signing in.
        </p>
        <p className="font-mono font-extrabold text-4xl tracking-[0.2em] text-center bg-primary/5 border-2 border-primary py-6">
          {state.code.user_code}
        </p>
        <button
          type="button"
          onClick={() => window.open(state.code.verification_uri, '_blank', 'noopener,noreferrer')}
          className="w-full font-display font-bold tracking-widest uppercase text-sm bg-primary text-white border-2 border-primary px-6 py-3 hover:bg-primary-hover hover:border-primary-hover transition-colors"
        >
          Open GitHub
        </button>
        <p className="text-xs text-ink-muted text-center">Waiting for confirmation...</p>
      </div>
    );
  }

  if (state.step === 'error') {
    return (
      <div className="space-y-4">
        <p className="text-danger text-sm">{state.message}</p>
        <button
          type="button"
          onClick={() => setState({ step: 'idle' })}
          className="font-display font-bold tracking-widest uppercase text-sm bg-primary text-white border-2 border-primary px-6 py-3 hover:bg-primary-hover hover:border-primary-hover transition-colors"
        >
          Start again
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <p className="text-ink-muted max-w-prose">
        Sign in with your GitHub account. Click the button, then read and enter a short code
        on github.com. No token to create or paste.
      </p>
      <button
        type="button"
        disabled={state.step === 'requesting'}
        onClick={start}
        className="font-display font-bold tracking-widest uppercase text-sm bg-primary text-white border-2 border-primary px-6 py-3 hover:bg-primary-hover hover:border-primary-hover disabled:opacity-50 transition-colors"
      >
        {state.step === 'requesting' ? 'Starting...' : 'Sign in with GitHub'}
      </button>
    </div>
  );
}

export function Login() {
  const env = authEnv();
  const strategy = availableStrategy(env);
  const { startupError } = useAuth();

  return (
    <Shell>
      {startupError && <p className="text-danger text-sm mb-6">{startupError}</p>}
      {strategy === 'device' ? (
        <DevicePanel proxyUrl={env.proxyUrl as string} clientId={env.clientId as string} />
      ) : (
        <TokenPanel />
      )}
    </Shell>
  );
}
