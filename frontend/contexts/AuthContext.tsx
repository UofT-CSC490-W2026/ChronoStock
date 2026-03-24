"use client";

import React, { createContext, useContext, useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface User {
  id: string;
  email: string;
}

interface AuthContextValue {
  user: User | null;
  token: string | null;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function isMockAuthEnabled(): boolean {
  return process.env.NEXT_PUBLIC_MOCK_AUTH === "true";
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);

  // Restore session on mount
  useEffect(() => {
    const stored = localStorage.getItem("chrono_token");
    if (!stored) return;

    if (isMockAuthEnabled()) {
      const storedUser = localStorage.getItem("chrono_user");
      if (storedUser) {
        try {
          setUser(JSON.parse(storedUser));
          setToken(stored);
        } catch {
          localStorage.removeItem("chrono_token");
          localStorage.removeItem("chrono_user");
        }
      }
      return;
    }

    // Real auth: verify token with backend
    fetch(`${API_BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${stored}` },
    })
      .then((res) => {
        if (!res.ok) throw new Error("Unauthorized");
        return res.json() as Promise<User>;
      })
      .then((u) => {
        setUser(u);
        setToken(stored);
      })
      .catch(() => {
        localStorage.removeItem("chrono_token");
      });
  }, []);

  async function login(email: string, password: string): Promise<void> {
    if (isMockAuthEnabled()) {
      const fakeToken = "mock-token-" + Math.random().toString(36).slice(2);
      const fakeUser: User = { id: "mock-id", email };
      localStorage.setItem("chrono_token", fakeToken);
      localStorage.setItem("chrono_user", JSON.stringify(fakeUser));
      setToken(fakeToken);
      setUser(fakeUser);
      return;
    }

    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error((err as { detail?: string }).detail ?? "Login failed");
    }
    const { access_token } = await res.json() as { access_token: string };

    localStorage.setItem("chrono_token", access_token);
    setToken(access_token);

    const meRes = await fetch(`${API_BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${access_token}` },
    });
    const me = await meRes.json() as User;
    setUser(me);
  }

  async function signup(email: string, password: string): Promise<void> {
    if (isMockAuthEnabled()) {
      const fakeToken = "mock-token-" + Math.random().toString(36).slice(2);
      const fakeUser: User = { id: "mock-id-" + Math.random().toString(36).slice(2), email };
      localStorage.setItem("chrono_token", fakeToken);
      localStorage.setItem("chrono_user", JSON.stringify(fakeUser));
      setToken(fakeToken);
      setUser(fakeUser);
      return;
    }

    const res = await fetch(`${API_BASE}/auth/signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error((err as { detail?: string }).detail ?? "Signup failed");
    }
    const { access_token } = await res.json() as { access_token: string };

    localStorage.setItem("chrono_token", access_token);
    setToken(access_token);

    const meRes = await fetch(`${API_BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${access_token}` },
    });
    const me = await meRes.json() as User;
    setUser(me);
  }

  function logout(): void {
    localStorage.removeItem("chrono_token");
    localStorage.removeItem("chrono_user");
    setToken(null);
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, token, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
