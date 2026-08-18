import { SignUp } from "@clerk/nextjs";
import { notFound } from "next/navigation";
import { blueprintAuthMode } from "../../../lib/auth-mode";

export default function SignUpPage() {
  if (blueprintAuthMode() !== "clerk") notFound();
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#0f1014] px-4 py-12 text-white">
      <SignUp routing="path" path="/sign-up" signInUrl="/sign-in" />
    </main>
  );
}
