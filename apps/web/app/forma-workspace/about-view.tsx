import { ArrowUpRight, Cpu, Handshake, ShieldCheck } from "lucide-react";
import LegalFooter from "../../components/legal-footer";
import PartnerLogoMarquee from "../../components/partner-logo-marquee";
import { legalContactEmail, legalEntityName } from "../../lib/legal-docs";
import { aboutMarqueePartners } from "../../lib/partners";

export default function AboutView() {
  return (
    <div className="font-sans text-zinc-100">
      <div className="mb-6">
        <div className="flex min-w-0 items-center gap-2">
          <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
            <Handshake className="h-3 w-3" />
            Workspace
          </span>
          <h1 className="truncate text-sm font-semibold tracking-tight text-zinc-100">About us</h1>
        </div>
        <p className="mt-2 text-sm leading-6 text-zinc-500">
          CAID Technologies, Forma, partners, and legal resources.
        </p>
      </div>

      <section className="grid gap-8 pb-10 lg:grid-cols-[0.82fr_1.18fr] lg:items-end">
        <div>
          <p className="text-sm font-medium text-zinc-500">{legalEntityName}</p>
          <h2 className="mt-4 text-4xl font-semibold leading-tight text-zinc-100 sm:text-6xl">About Forma</h2>
        </div>
        <div className="max-w-2xl text-base leading-7 text-zinc-500 lg:justify-self-end">
          Forma helps builders turn early hardware ideas into structured project plans with parts, wiring, validation, build notes, and generated artifacts.
          <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
            <a href={`mailto:${legalContactEmail}`} className="text-cyan-300 hover:text-zinc-100">
              {legalContactEmail}
            </a>
            <a
              href="https://www.caid-technologies.com/"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-cyan-300 hover:text-zinc-100"
            >
              CAID Technologies
              <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
            </a>
          </div>
        </div>
      </section>

      <section className="grid gap-3 pb-10 md:grid-cols-3">
        <div className="rounded-xl border border-white/5 bg-[#181b22] p-5">
          <Cpu className="h-5 w-5 text-cyan-300" />
          <h2 className="mt-4 text-sm font-semibold uppercase tracking-[0.18em] text-zinc-100">Hardware Planning</h2>
          <p className="mt-3 text-sm leading-6 text-zinc-500">Project generation for low-voltage maker hardware, structured around traceable artifacts.</p>
        </div>
        <div className="rounded-xl border border-white/5 bg-[#181b22] p-5">
          <ShieldCheck className="h-5 w-5 text-emerald-400" />
          <h2 className="mt-4 text-sm font-semibold uppercase tracking-[0.18em] text-zinc-100">Safety First</h2>
          <p className="mt-3 text-sm leading-6 text-zinc-500">Forma keeps safety constraints, validation notes, and known unknowns visible in the workflow.</p>
        </div>
        <div className="rounded-xl border border-white/5 bg-[#181b22] p-5">
          <Handshake className="h-5 w-5 text-cyan-300" />
          <h2 className="mt-4 text-sm font-semibold uppercase tracking-[0.18em] text-zinc-100">Partners</h2>
          <p className="mt-3 text-sm leading-6 text-zinc-500">Infrastructure partners support model, media, and deployment workflows across the product.</p>
        </div>
      </section>

      <section className="pb-10">
        <PartnerLogoMarquee partners={aboutMarqueePartners} hrefPrefix="/partners" />
      </section>

      <LegalFooter />
    </div>
  );
}
