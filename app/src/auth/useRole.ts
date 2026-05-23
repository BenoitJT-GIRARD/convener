import { useEffect, useState } from 'react';
import { useAuth } from './AuthContext';
import { useData } from '../data/DataContext';
import { detectRole } from './role';
import { isDemoMode } from '../data/demo';

export function useRole(): 'board' | 'organizer' | null {
  const { token, login } = useAuth();
  const { config } = useData();
  const [role, setRole] = useState<'board' | 'organizer' | null>(null);
  useEffect(() => {
    if (!token || !login) {
      setRole(null);
      return;
    }
    if (isDemoMode()) {
      setRole('board');
      return;
    }
    detectRole(login, token, config).then(setRole);
  }, [token, login, config]);
  return role;
}
