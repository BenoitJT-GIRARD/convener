import { Outlet } from 'react-router-dom';
import { Nav } from './Nav';

export function Layout() {
  return (
    <div className="flex min-h-screen">
      <Nav />
      <main className="flex-1 max-w-content mx-auto p-8">
        <Outlet />
      </main>
    </div>
  );
}
