'use client';

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { apiClient, User } from '@/lib/api';
import { logger, redactUserData } from '@/lib/logger';

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check if user is already logged in
    const loadUser = async () => {
      // Only attempt to load user if token exists
      if (!apiClient.hasToken()) {
        logger.log('[AuthContext] No token found, skipping user load');
        setLoading(false);
        return;
      }

      try {
        logger.log('[AuthContext] Loading current user');
        const currentUser = await apiClient.getCurrentUser();
        logger.log('[AuthContext] User loaded:', redactUserData(currentUser));
        setUser(currentUser);
      } catch (error) {
        logger.log('[AuthContext] Failed to load user, clearing token');
        // Not logged in or token expired
        apiClient.clearToken();
      } finally {
        setLoading(false);
      }
    };

    loadUser();
  }, []);

  const login = async (email: string, password: string) => {
    logger.log('[AuthContext] Attempting login');
    await apiClient.login(email, password);
    const currentUser = await apiClient.getCurrentUser();
    logger.log('[AuthContext] Login successful:', redactUserData(currentUser));
    setUser(currentUser);
  };

  const logout = () => {
    logger.log('[AuthContext] Logging out');
    apiClient.logout();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
