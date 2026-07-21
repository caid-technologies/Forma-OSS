import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { deployedAuthRequired } from "../lib/deployed-auth";
import "./globals.css";

export const metadata: Metadata = {
  title: "Forma | Build Hardware from Ideas",
  description: "Upload an image or describe an idea to generate parts, wiring, cost, and assembly notes.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const authRequired = deployedAuthRequired();
  return (
    <ClerkProvider>
      <html lang="en">
        <body data-auth-required={authRequired ? "true" : "false"}>
          {children}
        </body>
      </html>
    </ClerkProvider>
  );
}
