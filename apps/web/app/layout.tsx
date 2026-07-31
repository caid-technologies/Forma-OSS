import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { blueprintAuthMode } from "../lib/auth-mode";
import { FormaAuthProvider } from "../lib/forma-auth";
import { themeBootstrapScript } from "../lib/theme";
import { ThemeProvider } from "../lib/theme-provider";
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
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrapScript }} />
      </head>
      <body data-auth-mode={authMode} data-auth-required={authMode === "clerk" ? "true" : "false"}>
        <ThemeProvider>
          <FormaAuthProvider mode={authMode}>{children}</FormaAuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
  return authMode === "clerk" ? <ClerkProvider>{document}</ClerkProvider> : document;
}
