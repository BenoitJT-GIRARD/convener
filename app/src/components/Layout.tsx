import { Outlet } from 'react-router-dom';
import { TopTabs } from './TopTabs';

export function Layout() {
  return (
    <div className="max-w-content mx-auto">
      <TopTabs />
      <main><Outlet /></main>
    </div>
  );
}
