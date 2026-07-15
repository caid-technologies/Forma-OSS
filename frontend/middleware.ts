import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

// Auth is only enforced in hosted deployments. NEXT_PUBLIC_* vars are inlined
// at build time, so OSS/self-hosted builds without this flag (or without any
// Clerk keys) get a pass-through middleware.
const deploymentEnabled = /^(1|true|yes|on)$/i.test(
  process.env.NEXT_PUBLIC_BLUEPRINT_DEPLOYMENT?.trim() ?? "",
);

const isPublicRoute = createRouteMatcher([
  "/about(.*)",
  "/legal(.*)",
  "/partners(.*)",
  "/sign-in(.*)",
  "/sign-up(.*)",
]);

export default deploymentEnabled
  ? clerkMiddleware(async (auth, req) => {
      if (!isPublicRoute(req)) {
        // Redirects signed-out visitors to the Clerk sign-in page and back.
        await auth.protect();
      }
    })
  : function middleware() {
      return NextResponse.next();
    };

export const config = {
  matcher: [
    // Skip Next.js internals and all static files, unless found in search params
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // Always run for API routes
    "/(api|trpc)(.*)",
    // Clerk auto-proxy path
    "/__clerk/:path*",
  ],
};
