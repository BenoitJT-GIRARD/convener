import { afterEach, describe, expect, it } from 'vitest';

/**
 * Contract test for the embedded-in-MkDocs mount logic in src/main.tsx.
 * The app must mount on either:
 *   - `#app-root` (when embedded as a MkDocs page, see docs/team-app.md), or
 *   - `#root` (when running standalone via `vite dev`).
 * If both are present, `#app-root` wins.
 */

function pickMountElement(): HTMLElement | null {
  return document.getElementById('app-root') ?? document.getElementById('root');
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('fusion: mount target selection', () => {
  it('prefers #app-root when both exist', () => {
    document.body.innerHTML = '<div id="root"></div><div id="app-root"></div>';
    expect(pickMountElement()?.id).toBe('app-root');
  });

  it('falls back to #root when only #root exists', () => {
    document.body.innerHTML = '<div id="root"></div>';
    expect(pickMountElement()?.id).toBe('root');
  });

  it('uses #app-root when only #app-root exists', () => {
    document.body.innerHTML = '<div id="app-root"></div>';
    expect(pickMountElement()?.id).toBe('app-root');
  });

  it('returns null when neither exists (no silent failure)', () => {
    expect(pickMountElement()).toBeNull();
  });
});
