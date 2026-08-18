import { useEffect, useState } from 'react';
import { useAuth } from './AuthContext';
import { useData } from '../data/DataContext';
import { detectRole } from './role';
import { isDemoMode } from '../data/demo';

export function useRole(): 'board' | 'organizer' | null {
  const { token, login } = useAuth();
  const { config } = useData();
  // Only the async lookup (`detectRole`) needs state: the "no session" and
  // "demo mode" cases are pure, synchronous derivations of the current props,
  // so they're computed directly during render instead of via setState in an
  // effect.
  const [detectedRole, setDetectedRole] = useState<'board' | 'organizer' | null>(null);

  useEffect(() => {
    if (!token || !login || isDemoMode()) return;
    let cancelled = false;
    detectRole(login, token, config).then(r => {
      if (!cancelled) setDetectedRole(r);
    });
    return () => {
      cancelled = true;
    };
  }, [token, login, config]);

  if (!token || !login) return null;
  if (isDemoMode()) return 'board';
  return detectedRole;
}
