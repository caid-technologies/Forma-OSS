import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { ArrowLeft, ArrowUpRight, Cpu, Handshake } from "lucide-react";
import PartnerLogoMarquee from "../../components/partner-logo-marquee";
import { partners } from "../../lib/partners";

export const metadata: Metadata = {
  title: "Partners | Forma",
  description: "Forma partners and infrastructure collaborators.",
};

export default function PartnersPage() {
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
          <Handshake className="h-4 w-4 text-cyan-300" />
          Partners
        </div>
      </div>

      <section className="mx-auto grid w-full max-w-6xl gap-8 py-12 lg:grid-cols-[0.8fr_1.2fr] lg:items-end">
        <div>
          <p className="text-sm font-medium text-slate-500">Forma network</p>
          <h1 className="mt-4 text-4xl font-semibold leading-tight text-white sm:text-6xl">Partners</h1>
        </div>
        <p className="max-w-2xl text-base leading-7 text-slate-400 lg:justify-self-end">
          Infrastructure, tooling, and ecosystem collaborators that help builders move faster from idea to working systems.
        </p>
      </section>

      <section className="mx-auto w-full max-w-6xl pb-10">
        <PartnerLogoMarquee partners={partners} />
      </section>

      <section className="mx-auto w-full max-w-6xl">
        {partners.map((partner) => (
          <article
            key={partner.name}
            id={partner.slug}
            className="grid scroll-mt-6 gap-6 border border-[#2c2f37] bg-[#17181d] p-5 shadow-2xl shadow-black/25 md:grid-cols-[320px_1fr] md:p-6"
          >
            <div className="flex min-h-44 items-center justify-center border border-[#2c2f37] bg-black p-8">
              <Image
                src={partner.logo}
                alt={`${partner.name} logo`}
                width={800}
                height={176}
                className="h-auto w-full max-w-[260px]"
                priority
              />
            </div>

            <div className="min-w-0">
              <div className="inline-flex items-center gap-2 border border-cyan-300/30 bg-cyan-300/10 px-3 py-1.5 text-xs font-black uppercase text-cyan-200">
                <Cpu className="h-4 w-4" />
                AI Infrastructure
              </div>
              <h2 className="mt-5 text-2xl font-semibold text-white">{partner.name}</h2>
              <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-400">{partner.summary}</p>
              <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-500">{partner.relationship}</p>
              <Link
                href={partner.href}
                target="_blank"
                rel="noreferrer"
                className="mt-6 inline-flex h-11 items-center justify-center gap-2 bg-white px-4 text-sm font-semibold text-black transition hover:bg-slate-200"
              >
                Start with GMI Cloud
                <ArrowUpRight className="h-4 w-4" />
              </Link>
            </div>
          </article>
        ))}
      </section>
    </main>
  );
}
