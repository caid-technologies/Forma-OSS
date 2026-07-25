"use client";

import React, { createContext, useContext, useMemo } from "react";
import { UserButton, useAuth, useClerk, useUser } from "@clerk/nextjs";
import type { BlueprintAuthMode } from "./auth-mode";

type OpenSignInOptions = { redirectUrl?: string };

type FormaAuthValue = {
  mode: BlueprintAuthMode;
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
  return <FormaAuthContext.Provider value={value}>{children}</FormaAuthContext.Provider>;
}

export function FormaAuthProvider({
  mode,
  children,
}: {
  mode: BlueprintAuthMode;
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
