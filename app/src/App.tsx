import { HashRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { Login } from './auth/Login';
import { Layout } from './components/Layout';
import { DataProvider } from './data/DataContext';
import { Inbox } from './screens/Inbox';
import { Pipeline } from './screens/Pipeline';
import { Agenda } from './screens/Agenda';
import { Archive } from './screens/Archive';
import { Handbook } from './screens/Handbook';
import { Templates } from './screens/Templates';
import { SpeakerPage } from './screens/SpeakerPage';

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
          <Route path="handbook" element={<Handbook />} />
          <Route path="templates" element={<Templates />} />
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
        <Shell />
      </HashRouter>
    </AuthProvider>
  );
}
