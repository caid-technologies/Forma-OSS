import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

const Auth = createContext({ authRequired: true, isLoaded: true, isSignedIn: true,
  hasIdentity: true, identityKey: "alice", getToken: async (): Promise<string | null> => "alice",
  openSignIn: (_options?: { redirectUrl?: string }) => {} });

export function useFormaAuth() { return useContext(Auth); }
export function AuthFixture({ children }: { children: ReactNode }) {
  const [identity, setIdentity] = useState("alice");
  const value = useMemo(() => ({ authRequired: true, isLoaded: true, isSignedIn: true,
    hasIdentity: true, identityKey: identity, getToken: async () => identity, openSignIn: () => {} }), [identity]);
  return <Auth.Provider value={value}>
    <button onClick={() => setIdentity("bob")}>Switch to Bob</button>
    <button onClick={() => setIdentity("alice")}>Switch to Alice</button>
    {children}
  </Auth.Provider>;
}
