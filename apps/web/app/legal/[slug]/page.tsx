import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, FileText } from "lucide-react";
import {
  getLegalDocument,
  legalDocuments,
  legalEffectiveDate,
  legalEntityName,
  legalLastUpdated,
} from "../../../lib/legal-docs";

type LegalDocumentPageProps = {
  params: {
    slug: string;
  };
};

export function generateStaticParams() {
  return legalDocuments.map((document) => ({ slug: document.slug }));
}

export function generateMetadata({ params }: LegalDocumentPageProps): Metadata {
  const document = getLegalDocument(params.slug);
  if (!document) return {};
  return {
    title: `${document.title} | Forma`,
    description: document.summary,
  };
}

export default function LegalDocumentPage({ params }: LegalDocumentPageProps) {
  const document = getLegalDocument(params.slug);
  if (!document) notFound();

  return (
    <main className="min-h-screen bg-[#141519] px-5 py-5 font-sans text-slate-100">
      <div className="mx-auto flex w-full max-w-4xl items-center justify-between gap-3 border-b border-[#292b31] pb-5">
        <Link
          href="/legal"
          className="inline-flex h-11 items-center gap-2 border border-[#2c2f37] px-3 text-xs font-black uppercase tracking-widest text-slate-400 hover:bg-white hover:text-black"
        >
          <ArrowLeft className="h-4 w-4" />
          Legal
        </Link>
        <div className="inline-flex h-11 items-center gap-2 border border-[#2c2f37] px-3 text-xs font-black uppercase tracking-widest text-slate-400">
          <FileText className="h-4 w-4 text-cyan-300" />
          Policy
        </div>
      </div>

      <article className="mx-auto w-full max-w-4xl py-12">
        <p className="text-sm font-medium text-slate-500">{legalEntityName}</p>
        <h1 className="mt-4 text-4xl font-semibold leading-tight text-white sm:text-5xl">{document.title}</h1>
        <p className="mt-5 max-w-3xl text-base leading-7 text-slate-400">{document.summary}</p>
        <div className="mt-6 flex flex-wrap gap-2 text-xs font-semibold uppercase tracking-widest text-slate-500">
          <span className="border border-[#2c2f37] px-3 py-1.5">Last updated {legalLastUpdated}</span>
          <span className="border border-[#2c2f37] px-3 py-1.5">Effective {legalEffectiveDate}</span>
        </div>

        <div className="mt-10 space-y-9">
          {document.sections.map((section) => (
            <section key={section.heading} className="border-t border-[#292b31] pt-7">
              <h2 className="text-xl font-semibold text-white">{section.heading}</h2>
              {section.paragraphs?.map((paragraph) => (
                <p key={paragraph} className="mt-4 text-sm leading-7 text-slate-400">
                  {paragraph}
                </p>
              ))}
              {section.bullets && (
                <ul className="mt-4 space-y-3 text-sm leading-6 text-slate-400">
                  {section.bullets.map((bullet) => (
                    <li key={bullet} className="flex gap-3">
                      <span className="mt-2 h-1.5 w-1.5 shrink-0 bg-cyan-300" />
                      <span>{bullet}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ))}
        </div>
      </article>
    </main>
  );
}
