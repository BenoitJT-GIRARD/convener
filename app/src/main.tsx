import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { instanceIdentity } from './instance';
import './index.css';

// Whose cockpit this is. `index.html` carries the product's own name so
// that the tab is never blank before this runs; the instance's name comes
// from `config/instance.json`, which only reaches the browser through
// `vite.config.ts`'s own define (see `src/instance.ts`).
const instance = instanceIdentity();
document.title = `${instance.short_name} · ${instance.series}`;

const mountEl = document.getElementById('root');
if (mountEl) {
  createRoot(mountEl).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
