'use client';

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { apiClient, User } from '@/lib/api';

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
      try {
        console.log('[AuthContext] Loading user...');
        console.log('[AuthContext] Token present:', !!apiClient['token']);

        const currentUser = await apiClient.getCurrentUser();
        console.log('[AuthContext] User loaded successfully:', currentUser);
        setUser(currentUser);
      } catch (error) {
        // Not logged in or token expired
        console.error('[AuthContext] Failed to load user:', error);
        console.log('[AuthContext] Clearing token');
        apiClient.clearToken();
      } finally {
        setLoading(false);
        console.log('[AuthContext] Loading complete');
      }
    };

    loadUser();
  }, []);

  const login = async (email: string, password: string) => {
    await apiClient.login(email, password);
    const currentUser = await apiClient.getCurrentUser();
    setUser(currentUser);
  };

  const logout = () => {
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
