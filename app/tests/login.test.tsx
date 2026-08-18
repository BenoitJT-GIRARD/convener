import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AuthProvider } from '../src/auth/AuthContext';
import { Login } from '../src/auth/Login';

describe('Login', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('shows an error when the token is rejected', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
    render(
      <AuthProvider>
        <Login />
      </AuthProvider>,
    );
    fireEvent.change(screen.getByPlaceholderText('github_pat_...'), {
      target: { value: 'bad-token' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Sign in/ }));
    await waitFor(() => expect(screen.getByText(/did not work/)).toBeInTheDocument());
  });

  it('signs in successfully with no visible error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ login: 'alice' }) }),
    );
    render(
      <AuthProvider>
        <Login />
      </AuthProvider>,
    );
    fireEvent.change(screen.getByPlaceholderText('github_pat_...'), {
      target: { value: 'good-token' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Sign in/ }));
    await waitFor(() => expect(localStorage.getItem('convener.token')).toBe('good-token'));
    expect(screen.queryByText(/did not work/)).not.toBeInTheDocument();
  });

  it('activates demo mode and reloads when the demo button is clicked', () => {
    const reloadSpy = vi.fn();
    const originalLocation = window.location;
    // @ts-expect-error -- jsdom's window.location isn't directly replaceable
    delete window.location;
    // @ts-expect-error -- minimal stand-in, only `reload` is exercised here
    window.location = { ...originalLocation, reload: reloadSpy };

    render(
      <AuthProvider>
        <Login />
      </AuthProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: /View a live demo/ }));
    expect(localStorage.getItem('convener.demo')).toBe('1');
    expect(reloadSpy).toHaveBeenCalled();

    window.location = originalLocation;
  });
});
