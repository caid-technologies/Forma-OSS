import { SignUp } from "@clerk/nextjs";
import { notFound } from "next/navigation";
import PublicAppShell from "../../../components/public-app-shell";
import { formaAuthMode } from "../../../lib/auth-mode";

export default function SignUpPage() {
  if (formaAuthMode() !== "clerk") notFound();
  return (
    <PublicAppShell
      badge="Account"
      title="Sign up"
    >
      <div className="flex justify-center py-8">
        <SignUp routing="path" path="/sign-up" signInUrl="/sign-in" />
      </div>
    </PublicAppShell>
  );
}
