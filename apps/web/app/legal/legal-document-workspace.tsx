"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Search } from "lucide-react";
import PublicAppShell, { PUBLIC_CARD_CLASS } from "../../components/public-app-shell";
import {
  documentsForSlugs,
  legalDocumentMatchesQuery,
  legalEffectiveDate,
  legalEntityName,
  legalLastUpdated,
  primaryLegalSlugs,
  secondaryLegalSlugs,
  type LegalDocument,
} from "../../lib/legal-docs";

const navGroups = [
  { title: "Policies", slugs: primaryLegalSlugs },
  { title: "Reporting", slugs: secondaryLegalSlugs },
] as const;

export default function LegalDocumentWorkspace({ document }: { document: LegalDocument }) {
  const [query, setQuery] = useState("");

  const groups = useMemo(
    () =>
      navGroups
        .map((group) => ({
          ...group,
          documents: documentsForSlugs(group.slugs).filter((item) => legalDocumentMatchesQuery(item, query)),
        }))
        .filter((group) => group.documents.length > 0),
    [query],
  );

  return (
    <PublicAppShell
      badge="General"
      title="Legal"
      homeHref="/about"
      homeLabel="About"
    >
      <section className="grid gap-5 md:grid-cols-[240px_minmax(0,1fr)]">
        <aside className={`h-fit min-h-0 ${PUBLIC_CARD_CLASS} md:sticky md:top-4`}>
          <div className="border-b border-[#2c2f37] px-3 py-3">
            <div className="text-sm font-semibold text-white">Documents</div>
            <p className="mt-1 text-[11px] leading-4 text-slate-400">
              {legalEntityName}
            </p>
            <label className="mt-3 flex h-9 items-center gap-2 rounded-lg border border-[#2c2f37] bg-[#101115] px-3 focus-within:border-emerald-500">
              <Search className="h-3.5 w-3.5 shrink-0 text-slate-600" />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search policies"
                aria-label="Search legal documents"
                className="h-full min-w-0 flex-1 bg-transparent text-sm text-slate-200 outline-none placeholder:text-slate-600"
              />
            </label>
          </div>

          <nav aria-label="Legal documents" className="max-h-[calc(100vh-220px)] space-y-4 overflow-y-auto p-2">
            {groups.length ? (
              groups.map((group) => (
                <section key={group.title} className="space-y-1">
                  <h2 className="px-2 pb-1 pt-1 text-[11px] font-medium text-slate-500">{group.title}</h2>
                  {group.documents.map((item) => {
                    const selected = item.slug === document.slug;
                    return (
                      <Link
                        key={item.slug}
                        href={`/legal/${item.slug}`}
                        aria-current={selected ? "page" : undefined}
                        title={item.summary}
                        className={`flex w-full items-center rounded-lg px-2 py-1.5 text-left transition ${
                          selected
                            ? "bg-emerald-500/10 font-medium text-emerald-400"
                            : "text-zinc-400 hover:bg-zinc-800/40 hover:text-zinc-200"
                        }`}
                      >
                        <span className="min-w-0 flex-1 truncate text-[13px]">{item.title}</span>
                      </Link>
                    );
                  })}
                </section>
              ))
            ) : (
              <p className="px-2 py-3 text-[11px] leading-5 text-slate-500">No documents match that search.</p>
            )}
          </nav>
        </aside>

        <article className={PUBLIC_CARD_CLASS}>
          <div className="flex flex-col gap-4 border-b border-[#2c2f37] px-5 py-4 xl:flex-row xl:items-start xl:justify-between">
            <div className="min-w-0">
              <p className="text-xs text-slate-500">{legalEntityName}</p>
              <h2 className="mt-1 text-lg font-semibold tracking-tight text-white">{document.title}</h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">{document.summary}</p>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2 text-[11px] font-medium text-slate-500">
              <span className="rounded-lg border border-[#2c2f37] px-2.5 py-1">Updated {legalLastUpdated}</span>
              <span className="rounded-lg border border-[#2c2f37] px-2.5 py-1">Effective {legalEffectiveDate}</span>
            </div>
          </div>

          <div className="space-y-8 p-5">
            {document.sections.map((section) => (
              <section key={section.heading}>
                <h3 className="text-sm font-medium text-white">{section.heading}</h3>
                {section.paragraphs?.map((paragraph) => (
                  <p key={paragraph} className="mt-2 text-sm leading-6 text-slate-400">
                    {paragraph}
                  </p>
                ))}
                {section.bullets ? (
                  <ul className="mt-3 space-y-2 text-sm leading-6 text-slate-400">
                    {section.bullets.map((bullet) => (
                      <li key={bullet} className="flex gap-3">
                        <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
                        <span>{bullet}</span>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </section>
            ))}
          </div>
        </article>
      </section>
    </PublicAppShell>
  );
}
