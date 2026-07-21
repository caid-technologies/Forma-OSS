import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, Cpu, Handshake, ShieldCheck } from "lucide-react";
import LegalFooter from "../../components/legal-footer";
import PartnerLogoMarquee from "../../components/partner-logo-marquee";
import { legalContactEmail, legalEntityName } from "../../lib/legal-docs";
import { partners } from "../../lib/partners";

export const metadata: Metadata = {
  title: "About Us | Forma",
  description: "About CAID Technologies, Forma, partners, and legal resources.",
};

export default function AboutPage() {
  return (
    <>
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
            <Cpu className="h-4 w-4 text-cyan-300" />
            About us
          </div>
        </div>

        <section className="mx-auto grid w-full max-w-6xl gap-8 py-12 lg:grid-cols-[0.82fr_1.18fr] lg:items-end">
          <div>
            <p className="text-sm font-medium text-slate-500">{legalEntityName}</p>
            <h1 className="mt-4 text-4xl font-semibold leading-tight text-white sm:text-6xl">About Forma</h1>
          </div>
          <div className="max-w-2xl text-base leading-7 text-slate-400 lg:justify-self-end">
            Forma helps builders turn early hardware ideas into structured project plans with parts, wiring, validation, build notes, and generated artifacts.
            <a href={`mailto:${legalContactEmail}`} className="mt-4 block text-sm text-cyan-200 hover:text-white">
              {legalContactEmail}
            </a>
          </div>
        </section>

        <section className="mx-auto grid w-full max-w-6xl gap-3 pb-10 md:grid-cols-3">
          <div className="border border-[#2c2f37] bg-[#17181d] p-5">
            <Cpu className="h-5 w-5 text-cyan-300" />
            <h2 className="mt-4 text-sm font-black uppercase tracking-[0.18em] text-white">Hardware Planning</h2>
            <p className="mt-3 text-sm leading-6 text-slate-500">Project generation for low-voltage maker hardware, structured around traceable artifacts.</p>
          </div>
          <div className="border border-[#2c2f37] bg-[#17181d] p-5">
            <ShieldCheck className="h-5 w-5 text-emerald-300" />
            <h2 className="mt-4 text-sm font-black uppercase tracking-[0.18em] text-white">Safety First</h2>
            <p className="mt-3 text-sm leading-6 text-slate-500">Forma keeps safety constraints, validation notes, and known unknowns visible in the workflow.</p>
          </div>
          <div className="border border-[#2c2f37] bg-[#17181d] p-5">
            <Handshake className="h-5 w-5 text-cyan-300" />
            <h2 className="mt-4 text-sm font-black uppercase tracking-[0.18em] text-white">Partners</h2>
            <p className="mt-3 text-sm leading-6 text-slate-500">Infrastructure partners support model, media, and deployment workflows across the product.</p>
          </div>
        </section>

        <section className="mx-auto w-full max-w-6xl pb-10">
          <PartnerLogoMarquee partners={partners} hrefPrefix="/partners" />
        </section>
      </main>
      <LegalFooter />
    </>
  );
}
