import { SignIn } from "@clerk/nextjs";
import { notFound } from "next/navigation";
import PublicAppShell from "../../../components/public-app-shell";
import { formaAuthMode } from "../../../lib/auth-mode";

export default function SignInPage() {
  if (formaAuthMode() !== "clerk") notFound();
  return (
    <PublicAppShell
      badge="Account"
      title="Sign in"
    >
      <div className="flex justify-center py-8">
        <SignIn routing="path" path="/sign-in" signUpUrl="/sign-up" />
      </div>
    </PublicAppShell>
  );
}
