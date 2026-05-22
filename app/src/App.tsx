import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { Login } from './auth/Login';
import { Layout } from './components/Layout';
import { DataProvider } from './data/DataContext';
import { Pipeline } from './screens/Pipeline';
import { SpeakerPage } from './screens/SpeakerPage';
import { EventPage } from './screens/EventPage';
import { Home } from './screens/Home';
import { Analytics } from './screens/Analytics';

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
          <Route path="analytics" element={<Analytics />} />
          <Route path="speakers/:id" element={<SpeakerPage />} />
          <Route path="events/:id" element={<EventPage />} />
        </Route>
      </Routes>
    </DataProvider>
  );
}

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter basename="/app"><Shell /></BrowserRouter>
    </AuthProvider>
  );
}
