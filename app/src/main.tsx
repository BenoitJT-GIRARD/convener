import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './index.css';

// Support both standalone (#root) and embedded-in-MkDocs (#app-root) mount points.
const mountEl = document.getElementById('app-root') ?? document.getElementById('root');
if (mountEl) {
  createRoot(mountEl).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
