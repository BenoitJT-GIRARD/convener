import { HashRouter, Route, Routes, useParams, useSearchParams } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { Login } from './auth/Login';
import { Layout } from './components/Layout';
import { DataProvider } from './data/DataContext';
import { Inbox } from './screens/Inbox';
import { Pipeline } from './screens/Pipeline';
import { Agenda } from './screens/Agenda';
import { Archive } from './screens/Archive';
import { Board } from './screens/Board';
import { Diversity } from './screens/Diversity';
import { Consent } from './screens/Consent';
import { Handbook } from './screens/Handbook';
import { Templates } from './screens/Templates';
import { SpeakerPage } from './screens/SpeakerPage';
import { NewSpeaker } from './screens/NewSpeaker';
import { SignupForm } from './signup/SignupForm';
import { VerifyPage } from './verify/VerifyPage';

/**
 * Everything the organiser cockpit needs: gated on `useAuth` before
 * `DataProvider` -- which itself needs a token to read the private
 * `example-cockpit` repository -- ever mounts. Nested here, and reached only
 * through `App`'s `/*` route below, precisely so a route that must work
 * with no account (see `App`) never passes through this gate at all.
 */
function Shell() {
  const { ready, token } = useAuth();
  if (!ready) return <div className="p-8 text-ink-muted">Loading…</div>;
  if (!token) return <Login />;
  return (
    <DataProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Inbox />} />
          <Route path="pipeline" element={<Pipeline />} />
          <Route path="agenda" element={<Agenda />} />
          <Route path="archive" element={<Archive />} />
          <Route path="board" element={<Board />} />
          <Route path="diversity" element={<Diversity />} />
          <Route path="consent" element={<Consent />} />
          <Route path="handbook" element={<Handbook />} />
          <Route path="templates" element={<Templates />} />
          <Route path="speakers/new" element={<NewSpeaker />} />
          <Route path="speakers/:id" element={<SpeakerPage />} />
        </Route>
      </Routes>
    </DataProvider>
  );
}

/**
 * `useParams` only resolves inside a matched route's own element, so this
 * reads it and keys `SignupForm` by it, forcing a full remount whenever the
 * event id in the URL changes. `HashRouter` makes that reachable without a
 * page load -- editing `#/signup/mrg-042` to `#/signup/mrg-043` in the
 * address bar re-runs `SignupForm`'s effect on the same mounted component
 * otherwise, and nothing there resets `keyState` back to `'loading'`: the
 * previous event's fetched key would still answer while the new event id
 * is what gets sent, producing a registration encrypted under a key that
 * cannot decrypt it and destroyed on the wrong event's retention date.
 * Remounting resets every hook `SignupForm` holds from scratch, which
 * closes the whole class rather than threading an `eventId` comparison
 * through each place `KeyState` is read.
 */
function SignupRoute() {
  const { eventId } = useParams<{ eventId: string }>();
  return <SignupForm key={eventId} />;
}

/**
 * The same remount discipline `SignupRoute` applies to `eventId`, applied
 * here to `identifier` *and* `token` together: editing either in the
 * address bar (or clicking a second verification link without a full page
 * load, which `HashRouter` makes reachable) must not leave `VerifyPage`'s
 * own effects mid-flight against a token or identifier that no longer
 * matches the URL -- a stale `sig`/`lookup` state briefly describing the
 * *previous* certificate while the new check is still running. Keying by
 * both, joined, forces a full remount -- and a fresh "Checking…" -- on any
 * change to either.
 */
function VerifyRoute() {
  const { identifier } = useParams<{ identifier: string }>();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  return <VerifyPage key={`${identifier ?? ''}::${token ?? ''}`} />;
}

export function App() {
  return (
    <AuthProvider>
      <HashRouter>
        <Routes>
          {/* Public, by construction: a participant registering for an
              event has no account, and nothing on this route ever reaches
              `Shell`'s auth gate above -- matched first, and never falls
              through to it. (`AuthProvider` still wraps the whole router,
              including this route -- it only reads `localStorage` and, for
              a legacy stored token, validates it; no participant data is
              involved, and this route never reaches `Shell` or
              `DataProvider`, which is the gate that actually matters here.) */}
          <Route path="/signup/:eventId" element={<SignupRoute />} />
          {/* Public, by construction, the same way `/signup/:eventId` is
              above: a stranger checking a certificate has no account
              either, and this route never reaches `Shell`'s auth gate.
              `certificate.VERIFICATION_BASE` ends `#/verify/`, matching
              this path exactly -- see `VerifyPage.tsx`'s own module
              comment for why the fragment is load-bearing for privacy,
              not only for GitHub Pages routing. */}
          <Route path="/verify/:identifier" element={<VerifyRoute />} />
          <Route path="/*" element={<Shell />} />
        </Routes>
      </HashRouter>
    </AuthProvider>
  );
}
