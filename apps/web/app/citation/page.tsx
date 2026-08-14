import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, ArrowUpRight, BookOpen, Code, GitCommit } from "lucide-react";

import LegalFooter from "../../components/legal-footer";
import CitationCopyButton from "./citation-copy-button";

const repositoryUrl = "https://github.com/caid-technologies/Forma-OSS";
const release = "v0.3.2";
const releaseUrl = `${repositoryUrl}/releases/tag/${release}`;

const plainTextCitation =
  "CAID Technologies, Inc. (2026). Forma OSS (Version 0.3.2) [Computer software]. GitHub. https://github.com/caid-technologies/Forma-OSS/releases/tag/v0.3.2";

const bibtexCitation = `@software{caid_forma_2026,
  author  = {{CAID Technologies, Inc.}},
  title   = {Forma OSS},
  version = {0.3.2},
  year    = {2026},
  url     = {https://github.com/caid-technologies/Forma-OSS/releases/tag/v0.3.2}
}`;

export const metadata: Metadata = {
  title: "Cite Forma | Forma",
  description: "Citation formats and reproducibility guidance for Forma OSS.",
};

export default function CitationPage() {
  return (
    <div className="flex min-h-screen flex-col bg-[#141519]">
      <main className="flex-1 px-5 py-5 font-sans text-slate-100">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-3 border-b border-[#292b31] pb-5">
          <Link
            href="/"
            className="inline-flex h-11 items-center gap-2 border border-[#2c2f37] px-3 text-xs font-black uppercase tracking-widest text-slate-400 hover:bg-white hover:text-black"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Forma
          </Link>
          <div className="inline-flex h-11 items-center gap-2 border border-[#2c2f37] px-3 text-xs font-black uppercase tracking-widest text-slate-400">
            <BookOpen className="h-4 w-4 text-cyan-300" aria-hidden="true" />
            Citation
          </div>
        </div>

        <section className="mx-auto grid w-full max-w-6xl gap-8 py-12 lg:grid-cols-[0.8fr_1.2fr] lg:items-end">
          <div>
            <p className="text-sm font-medium text-slate-500">Forma OSS</p>
            <h1 className="mt-4 text-4xl font-semibold leading-tight text-white sm:text-6xl">Cite Forma</h1>
          </div>
          <p className="max-w-2xl text-base leading-7 text-slate-400 lg:justify-self-end">
            If Forma supports your research, publication, or project, cite the software release you used. The examples below reference the current tagged release, {release}.
          </p>
        </section>

        <section className="mx-auto grid w-full max-w-6xl gap-4 pb-10">
          <CitationCard title="Plain text" value={plainTextCitation} language="text" />
          <CitationCard title="BibTeX" value={bibtexCitation} language="bibtex" />
        </section>

        <section className="mx-auto grid w-full max-w-6xl gap-4 pb-12 md:grid-cols-2">
          <article className="border border-[#2c2f37] bg-[#17181d] p-5 sm:p-6">
            <GitCommit className="h-5 w-5 text-cyan-300" aria-hidden="true" />
            <h2 className="mt-4 text-sm font-black uppercase tracking-[0.18em] text-white">Use the version you used</h2>
            <p className="mt-3 text-sm leading-6 text-slate-500">
              For reproducible work, replace {release} with the release tag or commit hash you actually used. Include an access date when required by your citation style.
            </p>
            <a
              href={`${repositoryUrl}/releases`}
              target="_blank"
              rel="noreferrer"
              className="mt-5 inline-flex items-center gap-1.5 text-sm font-semibold text-cyan-200 hover:text-white"
            >
              Browse Forma releases
              <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
            </a>
          </article>

          <article className="border border-[#2c2f37] bg-[#17181d] p-5 sm:p-6">
            <Code className="h-5 w-5 text-cyan-300" aria-hidden="true" />
            <h2 className="mt-4 text-sm font-black uppercase tracking-[0.18em] text-white">Repository</h2>
            <p className="mt-3 break-all font-mono text-sm leading-6 text-slate-500">{repositoryUrl}</p>
            <div className="mt-5 flex flex-wrap items-center gap-3">
              <CitationCopyButton value={repositoryUrl} label="Copy URL" />
              <a
                href={releaseUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-9 items-center gap-1.5 px-1 text-sm font-semibold text-cyan-200 hover:text-white"
              >
                View {release}
                <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
              </a>
            </div>
          </article>
        </section>

        <section className="mx-auto w-full max-w-6xl border-t border-[#292b31] py-6 text-xs leading-5 text-slate-500">
          Forma does not currently publish a DOI or a separate academic paper. Cite generated images, project artifacts, datasets, and third-party models separately when your venue requires it.
        </section>
      </main>
      <LegalFooter />
    </div>
  );
}

function CitationCard({ title, value, language }: { title: string; value: string; language: string }) {
  return (
    <article className="overflow-hidden border border-[#2c2f37] bg-[#17181d]">
      <div className="flex items-center justify-between gap-4 border-b border-[#2c2f37] px-4 py-3 sm:px-5">
        <div>
          <h2 className="text-sm font-black uppercase tracking-[0.18em] text-white">{title}</h2>
          <p className="mt-1 text-[10px] font-bold uppercase tracking-widest text-slate-600">{language}</p>
        </div>
        <CitationCopyButton value={value} label={`Copy ${title}`} />
      </div>
      <pre className="overflow-x-auto whitespace-pre-wrap break-words p-4 font-mono text-sm leading-6 text-slate-300 sm:p-5">
        <code>{value}</code>
      </pre>
    </article>
  );
}
