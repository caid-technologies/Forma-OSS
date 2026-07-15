import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";

export const metadata: Metadata = {
  title: "Blueprint | Build Hardware from Ideas",
  description: "Upload an image or describe an idea to generate parts, wiring, cost, and assembly notes.",
};

// Clerk is only active in hosted deployments; OSS/self-hosted builds run
// without any Clerk keys and skip the provider entirely.
const deploymentEnabled = /^(1|true|yes|on)$/i.test(
  process.env.NEXT_PUBLIC_BLUEPRINT_DEPLOYMENT?.trim() ?? "",
);

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const content = (
    <html lang="en">
      <body>
        {children}
      </body>
    </html>
  );

  return deploymentEnabled ? <ClerkProvider>{content}</ClerkProvider> : content;
}
