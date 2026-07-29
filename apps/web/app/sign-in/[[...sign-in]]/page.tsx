import { SignIn } from "@clerk/nextjs";
import { notFound } from "next/navigation";
import { blueprintAuthMode } from "../../../lib/auth-mode";

export default function SignInPage() {
  if (blueprintAuthMode() !== "clerk") notFound();
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#0f1014] px-4 py-12 text-white">
      <SignIn routing="path" path="/sign-in" signUpUrl="/sign-up" />
    </main>
  );
}
