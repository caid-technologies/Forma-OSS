import { SignIn } from "@clerk/nextjs";
import { notFound } from "next/navigation";

// Auth only exists in hosted deployments; OSS/self-hosted builds 404 here.
const deploymentEnabled = /^(1|true|yes|on)$/i.test(
  process.env.NEXT_PUBLIC_BLUEPRINT_DEPLOYMENT?.trim() ?? "",
);

export default function SignInPage() {
  if (!deploymentEnabled) notFound();
  return (
    <div className="flex min-h-screen items-center justify-center">
      <SignIn />
    </div>
  );
}
