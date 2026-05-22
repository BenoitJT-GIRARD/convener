import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';

function Placeholder({ name }: { name: string }) {
  return <h1 className="font-serif text-3xl">{name}</h1>;
}

export function App() {
  return (
    <BrowserRouter basename="/app">
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Placeholder name="Home" />} />
          <Route path="pipeline" element={<Placeholder name="Pipeline" />} />
          <Route path="analytics" element={<Placeholder name="Analytics" />} />
          <Route path="speakers/:id" element={<Placeholder name="Speaker" />} />
          <Route path="events/:id" element={<Placeholder name="Event" />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
