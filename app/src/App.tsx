import { HashRouter, Route, Routes } from 'react-router-dom';
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
import { Settings } from './screens/Settings';
import { SpeakerPage } from './screens/SpeakerPage';
import { NewSpeaker } from './screens/NewSpeaker';

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
          <Route path="settings" element={<Settings />} />
          <Route path="speakers/new" element={<NewSpeaker />} />
          <Route path="speakers/:id" element={<SpeakerPage />} />
        </Route>
      </Routes>
    </DataProvider>
  );
}

export function App() {
  return (
    <AuthProvider>
      <HashRouter>
        <Routes>
          {/* Registration used to be a public route here too
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
              route this replaced.

              The post-event survey (spec S:6) used to be the last public
              route left here (`/survey/:eventId`) -- phase 7 task 5
              extracted it too, into an island mounted on its own static
              page (`site/src/survey.njk`, `app/src/islands/survey/`), the
              identical D-18 move a third time. Unlike verification and
              like registration, this one *did* move onto a real, bare
              path: `survey_invite.SURVEY_BASE` carries only an event id,
              never a name or a token, so there was never a Referer-leak
              property tying it to a fragment in the first place (see that
              constant's own comment). This was the one asymmetry the
              security audit's web surface review named -- with this
              route gone, `App` (below) mounts nothing a visitor with no
              account is ever meant to reach; every route left is gated by
              `Shell`. */}
          <Route path="/*" element={<Shell />} />
        </Routes>
      </HashRouter>
    </AuthProvider>
  );
}
