"use client";

import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from "react";
import {
  authApi,
  tokenStorage,
  setTokenRefreshHandler,
  UserDto,
  TenantDto,
  ApiError,
} from "./api";

interface AuthContextType {
  user: UserDto | null;
  tenant: TenantDto | null;
  token: string | null;
  isLoading: boolean;
  error: string | null;
  isAuthenticated: boolean;
  login: (email: string, password: string, tenant_slug: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<boolean>;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

let activeRefreshPromise: Promise<string | null> | null = null;

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserDto | null>(null);
  const [tenant, setTenant] = useState<TenantDto | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const tokenRef = useRef<string | null>(null);
  tokenRef.current = token;

  const clearError = useCallback(() => setError(null), []);

  const executeRefresh = useCallback(async (): Promise<string | null> => {
    if (activeRefreshPromise) {
      return activeRefreshPromise;
    }

    activeRefreshPromise = (async () => {
      try {
        // Calls POST /auth/refresh with credentials: "include"
        // Browser automatically attaches HttpOnly refresh_token cookie
        const tokenResp = await authApi.refresh();
        setToken(tokenResp.access_token);
        tokenRef.current = tokenResp.access_token;
        const profile = await authApi.getMe(tokenResp.access_token);
        setUser(profile.user);
        setTenant(profile.tenant);
        return tokenResp.access_token;
      } catch {
        setToken(null);
        tokenRef.current = null;
        setUser(null);
        setTenant(null);
        tokenStorage.clearLegacyTokens();
        return null;
      } finally {
        activeRefreshPromise = null;
      }
    })();

    return activeRefreshPromise;
  }, []);

  const refreshSession = useCallback(async (): Promise<boolean> => {
    const newToken = await executeRefresh();
    return newToken !== null;
  }, [executeRefresh]);

  // Hook into apiFetch interceptor so that 401 on expired access tokens triggers transparent refresh
  useEffect(() => {
    setTokenRefreshHandler(executeRefresh);
    return () => setTokenRefreshHandler(null);
  }, [executeRefresh]);

  // Initialize auth state on client mount (session restoration after page reload)
  useEffect(() => {
    const initAuth = async () => {
      setIsLoading(true);
      // Clean up any stale localStorage tokens from prior phases
      tokenStorage.clearLegacyTokens();
      try {
        // Attempt to restore session using the HttpOnly refresh cookie
        await executeRefresh();
      } catch {
        setToken(null);
        setUser(null);
        setTenant(null);
      } finally {
        setIsLoading(false);
      }
    };

    initAuth();
  }, [executeRefresh]);

  const login = async (email: string, password: string, tenant_slug: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const tokens = await authApi.login({ email, password, tenant_slug });
      // Keep access token in React state memory only; refresh token is stored in HttpOnly cookie by backend
      setToken(tokens.access_token);
      tokenRef.current = tokens.access_token;
      tokenStorage.clearLegacyTokens();
      const profile = await authApi.getMe(tokens.access_token);
      setUser(profile.user);
      setTenant(profile.tenant);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.detail);
        throw err;
      } else {
        const msg = (err as Error).message || "Login failed. Please check credentials.";
        setError(msg);
        throw new Error(msg);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    setIsLoading(true);
    try {
      // POST /auth/logout with credentials: "include"
      // Backend clears the HttpOnly cookie and marks the session revoked in the database
      await authApi.logout(token || undefined);
    } catch {
      // Continue cleanup even if server logout errored
    } finally {
      setToken(null);
      tokenRef.current = null;
      setUser(null);
      setTenant(null);
      tokenStorage.clearLegacyTokens();
      setIsLoading(false);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        tenant,
        token,
        isLoading,
        error,
        isAuthenticated: !!token && !!user,
        login,
        logout,
        refreshSession,
        clearError,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
