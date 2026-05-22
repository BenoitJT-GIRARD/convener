import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { Login } from './auth/Login';
import { Layout } from './components/Layout';
import { DataProvider } from './data/DataContext';
import { Pipeline } from './screens/Pipeline';

function Placeholder({ name }: { name: string }) {
  return <h1 className="font-serif text-3xl">{name}</h1>;
}

function Shell() {
  const { ready, token } = useAuth();
  if (!ready) return <div className="p-8 text-ink-muted">Loading…</div>;
  if (!token) return <Login />;
  return (
    <DataProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Placeholder name="Home" />} />
          <Route path="pipeline" element={<Pipeline />} />
          <Route path="analytics" element={<Placeholder name="Analytics" />} />
          <Route path="speakers/:id" element={<Placeholder name="Speaker" />} />
          <Route path="events/:id" element={<Placeholder name="Event" />} />
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
