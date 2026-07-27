import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { blueprintAuthMode } from "../lib/auth-mode";
import { FormaAuthProvider } from "../lib/forma-auth";
import "./globals.css";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Forma | Build Hardware from Ideas",
  description: "Upload an image or describe an idea to generate parts, wiring, cost, and assembly notes.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const authMode = blueprintAuthMode();
  const document = (
    <html lang="en">
      <body data-auth-mode={authMode} data-auth-required={authMode === "clerk" ? "true" : "false"}>
        <FormaAuthProvider mode={authMode}>{children}</FormaAuthProvider>
      </body>
    </html>
  );
  return authMode === "clerk" ? <ClerkProvider>{document}</ClerkProvider> : document;
}
