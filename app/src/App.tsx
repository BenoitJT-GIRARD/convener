import { HashRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { Login } from './auth/Login';
import { Layout } from './components/Layout';
import { DataProvider } from './data/DataContext';
import { Home } from './screens/Home';
import { Pipeline } from './screens/Pipeline';
import { SpeakerPage } from './screens/SpeakerPage';

function Shell() {
  const { ready, token } = useAuth();
  if (!ready) return <div className="p-8 text-ink-muted">Loading…</div>;
  if (!token) return <Login />;
  return (
    <DataProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="pipeline" element={<Pipeline />} />
          <Route path="speakers/:id" element={<SpeakerPage />} />
        </Route>
      </Routes>
    </DataProvider>
  );
}

export function App() {
  return (
    <AuthProvider>
      <HashRouter><Shell /></HashRouter>
    </AuthProvider>
  );
}
