import { HashRouter, Route, Routes, useParams } from 'react-router-dom';
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
import { SurveyForm } from './survey/SurveyForm';

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

/** The same remount discipline `app/src/islands/signup/main.tsx::
 *  mountSignupIsland` gives the registration island (task 6 moved
 *  registration out of this application entirely -- see git history for
 *  the route this used to be), applied to the survey page for the
 *  identical reason: editing the event id in the address bar must reset
 *  `SurveyForm`'s own `keyState` rather than let a previous event's
 *  fetched key silently answer for a new one. */
function SurveyRoute() {
  const { eventId } = useParams<{ eventId: string }>();
  return <SurveyForm key={eventId} />;
}

export function App() {
  return (
    <AuthProvider>
      <HashRouter>
        <Routes>
          {/* Public, by construction: the post-event survey (spec S:6) is
              reached from a link in an e-mail, never from `Shell`'s own
              navigation, and a participant answering it has no account --
              matched first, and never falls through to `Shell`'s auth gate
              below. (`AuthProvider` still wraps the whole router, including
              this route -- it only reads `localStorage` and, for a legacy
              stored token, validates it; no participant data is involved,
              and this route never reaches `Shell` or `DataProvider`, which
              is the gate that actually matters here.)

              Registration used to be a public route here too
              (`/signup/:eventId`) -- task 6 extracted it into an island
              mounted on `site/src/event.njk` instead
              (`app/src/islands/signup/`), per D-18 ("static pages,
              interactivity in islands"): a visitor who wants to register no
              longer downloads this whole application to do it. See git
              history for the route this replaced.

              Certificate verification used to be a public route here too
              (`/verify/:identifier`, reading `?token=` off the URL) --
              task 7 extracted it into an island mounted on its own static
              page instead (`site/src/verify.njk`,
              `app/src/islands/verify/`), the identical move for the
              identical D-18 reason. That extraction did *not* also move
              onto a real, bare path the way registration's did:
              `certificate.VERIFICATION_BASE` still ends `#/`, because the
              token it carries names a person (`signing.PAYLOAD_FIELDS`'s
              `name` field), and a browser never sends a URL fragment in a
              request or a `Referer` header -- see that constant's own
              comment, and `app/src/islands/verify/VerifyPage.tsx`'s own
              module comment, for why losing the router when this route
              left did not lose that property. See git history for the
              route this replaced. */}
          <Route path="/survey/:eventId" element={<SurveyRoute />} />
          <Route path="/*" element={<Shell />} />
        </Routes>
      </HashRouter>
    </AuthProvider>
  );
}
