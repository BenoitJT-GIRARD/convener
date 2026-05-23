import { Outlet } from 'react-router-dom';
import { TopTabs } from './TopTabs';
import { isDemoMode, exitDemoMode } from '../data/demo';

function exitDemo() {
  exitDemoMode();
  window.location.reload();
}

export function Layout() {
  const demo = isDemoMode();
  return (
    <>
      {demo && (
        <div className="bg-accent text-white text-sm py-2 px-4">
          <div className="max-w-content mx-auto flex items-center justify-between">
            <span><strong>Demo mode</strong> — data is mocked, edits stay in this tab and don&rsquo;t persist.</span>
            <button onClick={exitDemo} className="underline">Exit demo</button>
          </div>
        </div>
      )}
      <div className="max-w-content mx-auto">
        <TopTabs />
        <main><Outlet /></main>
      </div>
    </>
  );
}
