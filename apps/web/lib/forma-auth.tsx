"use client";

import React, { createContext, useContext, useMemo } from "react";
import { UserButton, useAuth, useClerk, useUser } from "@clerk/nextjs";
import type { FormaAuthMode } from "./auth-mode";

type OpenSignInOptions = { redirectUrl?: string };

type FormaAuthValue = {
  mode: FormaAuthMode;
  authRequired: boolean;
  isLoaded: boolean;
  isSignedIn: boolean;
  hasIdentity: boolean;
  identityKey: string;
  userImageUrl: string | null;
  getToken: () => Promise<string | null>;
  openSignIn: (options?: OpenSignInOptions) => void;
};

const FormaAuthContext = createContext<FormaAuthValue | null>(null);

const localAuthValue: FormaAuthValue = {
  mode: "local",
  authRequired: false,
  isLoaded: true,
  isSignedIn: false,
  hasIdentity: true,
  identityKey: "local",
  userImageUrl: null,
  getToken: async () => null,
  openSignIn: () => undefined,
};

function ClerkAuthBridge({ children }: { children: React.ReactNode }) {
  const { getToken, isLoaded, isSignedIn, userId } = useAuth();
  const { openSignIn } = useClerk();
  const { user } = useUser();
  const lastResolvedIdentityRef = React.useRef<string | null>(null);
  const identityBoundaryKeyRef = React.useRef("initial-session");
  if (isLoaded) {
    const resolvedIdentity = userId || "signed-out";
    if (
      lastResolvedIdentityRef.current !== null
      && lastResolvedIdentityRef.current !== resolvedIdentity
    ) {
      // Remount on a real account transition, but not when Clerk merely
      // resolves the initial session after hydration.
      identityBoundaryKeyRef.current = `session:${resolvedIdentity}`;
    }
    lastResolvedIdentityRef.current = resolvedIdentity;
  }
  const value = useMemo<FormaAuthValue>(
    () => ({
      mode: "clerk",
      authRequired: true,
      isLoaded,
      isSignedIn: Boolean(isSignedIn),
      hasIdentity: Boolean(isSignedIn),
      identityKey: userId || (isSignedIn ? "clerk-signed-in" : "clerk-signed-out"),
      userImageUrl: user?.imageUrl || null,
      getToken: async () => (await getToken()) || null,
      openSignIn: (options) => {
        void openSignIn(options);
      },
    }),
    [getToken, isLoaded, isSignedIn, openSignIn, user?.imageUrl, userId]
  );
  return (
    <FormaAuthContext.Provider value={value}>
      <React.Fragment key={identityBoundaryKeyRef.current}>{children}</React.Fragment>
    </FormaAuthContext.Provider>
  );
}

export function FormaAuthProvider({
  mode,
  children,
}: {
  mode: FormaAuthMode;
  children: React.ReactNode;
}) {
  if (mode === "clerk") return <ClerkAuthBridge>{children}</ClerkAuthBridge>;
  return <FormaAuthContext.Provider value={localAuthValue}>{children}</FormaAuthContext.Provider>;
}

export function useFormaAuth() {
  const value = useContext(FormaAuthContext);
  if (!value) throw new Error("useFormaAuth must be used inside FormaAuthProvider.");
  return value;
}

export function FormaUserButton({ afterSignOutUrl = "/" }: { afterSignOutUrl?: string }) {
  const { mode, isSignedIn } = useFormaAuth();
  if (mode !== "clerk" || !isSignedIn) return null;
  return <UserButton afterSignOutUrl={afterSignOutUrl} />;
}
