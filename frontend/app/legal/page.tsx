import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, ArrowRight, FileText } from "lucide-react";
import { legalDocuments, legalEntityName, legalLastUpdated } from "../../lib/legal-docs";

export const metadata: Metadata = {
  title: "Legal | Forma",
  description: "Forma legal, privacy, safety, copyright, security, and accessibility documents.",
};

export default function LegalIndexPage() {
  return (
    <main className="min-h-screen bg-[#141519] px-5 py-5 font-sans text-slate-100">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-3 border-b border-[#292b31] pb-5">
        <Link
          href="/"
          className="inline-flex h-11 items-center gap-2 border border-[#2c2f37] px-3 text-xs font-black uppercase tracking-widest text-slate-400 hover:bg-white hover:text-black"
        >
          <ArrowLeft className="h-4 w-4" />
          Forma
        </Link>
        <div className="inline-flex h-11 items-center gap-2 border border-[#2c2f37] px-3 text-xs font-black uppercase tracking-widest text-slate-400">
          <FileText className="h-4 w-4 text-cyan-300" />
          Legal
        </div>
      </div>

      <section className="mx-auto grid w-full max-w-6xl gap-8 py-12 lg:grid-cols-[0.8fr_1.2fr] lg:items-end">
        <div>
          <p className="text-sm font-medium text-slate-500">{legalEntityName}</p>
          <h1 className="mt-4 text-4xl font-semibold leading-tight text-white sm:text-6xl">Legal</h1>
        </div>
        <p className="max-w-2xl text-base leading-7 text-slate-400 lg:justify-self-end">
          Terms, privacy, safety, acceptable use, copyright, security, and accessibility documents for Forma.
        </p>
      </section>

      <section className="mx-auto grid w-full max-w-6xl gap-3 pb-12 md:grid-cols-2">
        {legalDocuments.map((document) => (
          <Link
            key={document.slug}
            href={`/legal/${document.slug}`}
            className="group border border-[#2c2f37] bg-[#17181d] p-5 transition hover:border-slate-400 hover:bg-[#1d1f26]"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h2 className="text-lg font-semibold text-white">{document.title}</h2>
                <p className="mt-3 text-sm leading-6 text-slate-500">{document.summary}</p>
              </div>
              <ArrowRight className="mt-1 h-4 w-4 shrink-0 text-slate-500 transition group-hover:translate-x-1 group-hover:text-white" />
            </div>
          </Link>
        ))}
      </section>

      <section className="mx-auto w-full max-w-6xl border-t border-[#292b31] py-6 text-xs leading-5 text-slate-500">
        Last updated {legalLastUpdated}. Review the repository legal drafts before publication because address, governing law, and vendor-specific details may still need confirmation.
      </section>
    </main>
  );
}
