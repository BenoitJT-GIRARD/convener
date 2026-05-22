import { useState } from 'react';
import { useAuth } from './AuthContext';
import { Button } from '../components/Button';

export function Login() {
  const { signIn } = useAuth();
  const [token, setToken] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    const ok = await signIn(token.trim());
    setBusy(false);
    if (!ok) setErr('That token did not work. Check the scope and try again.');
  }

  return (
    <div className="max-w-md mx-auto py-16">
      <h1 className="font-serif text-3xl mb-6">Sign in</h1>
      <p className="text-ink-muted mb-4">
        The app uses your GitHub identity. You need a fine-grained personal access token
        with read/write access to the <code>workshop-series</code> repository.
      </p>
      <details className="mb-6 text-sm">
        <summary className="cursor-pointer text-primary">How to generate a token (one minute)</summary>
        <ol className="list-decimal pl-6 mt-2 space-y-1 text-ink-muted">
          <li>Open <a className="underline" href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noreferrer">github.com/settings/personal-access-tokens/new</a>.</li>
          <li>Resource owner: <code>The Example Collective</code>. Repository access: only <code>workshop-series</code>.</li>
          <li>Permissions: <em>Contents: read &amp; write</em>, <em>Issues: read &amp; write</em>.</li>
          <li>Generate, copy the token, paste below.</li>
        </ol>
      </details>
      <form onSubmit={submit} className="space-y-3">
        <input
          type="password" placeholder="github_pat_..."
          value={token} onChange={e => setToken(e.target.value)}
          className="w-full px-3 py-2 border border-border rounded-md bg-surface font-mono text-sm"
          required
        />
        <Button type="submit" disabled={busy}>{busy ? 'Checking…' : 'Sign in'}</Button>
        {err && <p className="text-danger text-sm">{err}</p>}
      </form>
    </div>
  );
}
