import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, ArrowUpRight, Cpu, Handshake, ShieldCheck } from "lucide-react";
import LegalFooter from "../../components/legal-footer";
import CaidLogo from "../../components/caid-logo";
import PartnerLogoMarquee from "../../components/partner-logo-marquee";
import { legalContactEmail, legalEntityName } from "../../lib/legal-docs";
import { aboutMarqueePartners } from "../../lib/partners";

export const metadata: Metadata = {
  title: "About Us | Forma",
  description: "About CAID Technologies, Forma, partners, and legal resources.",
};

export default function AboutPage() {
  return (
    <div className="flex min-h-screen flex-col bg-[#141519]">
      <main className="flex-1 px-5 py-5 font-sans text-slate-100">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-3 border-b border-[#292b31] pb-5">
          <Link
            href="/"
            className="inline-flex h-11 items-center gap-2 border border-[#2c2f37] px-3 text-xs font-black uppercase tracking-widest text-slate-400 hover:bg-white hover:text-black"
          >
            <ArrowLeft className="h-4 w-4" />
            Forma
          </Link>
          <div className="inline-flex h-11 items-center gap-2 border border-[#2c2f37] px-3 text-xs font-black uppercase tracking-widest text-slate-400">
            <CaidLogo className="h-6 w-11" sizes="44px" />
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
            <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
              <a href={`mailto:${legalContactEmail}`} className="text-cyan-200 hover:text-white">
                {legalContactEmail}
              </a>
              <a
                href="https://www.caid-technologies.com/"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-cyan-200 hover:text-white"
              >
                CAID Technologies
                <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
              </a>
            </div>
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

        <section className="mx-auto w-full max-w-6xl pb-10" aria-label="Try Parti">
          <a
            href="https://huggingface.co/spaces/caid-technologies/parti"
            target="_blank"
            rel="noreferrer"
            aria-label="Try Parti on Hugging Face"
            className="group inline-flex w-full flex-col items-center justify-center border border-[#2c2f37] bg-[#17181d] px-6 py-5 text-center transition hover:border-[#ffd21e]/70 hover:bg-[#ffd21e]/5 focus-visible:border-[#ffd21e] focus-visible:outline-none sm:w-52"
          >
            <HuggingFaceIcon className="h-10 w-10 text-[#ffd21e] transition-transform group-hover:scale-105" />
            <span className="mt-4 text-xs font-black uppercase tracking-[0.18em] text-white">Try Parti</span>
            <span className="mt-2 inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500 group-hover:text-[#ffd21e]">
              Hugging Face Space
              <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
            </span>
          </a>
        </section>

        <section className="mx-auto w-full max-w-6xl pb-10">
          <PartnerLogoMarquee partners={aboutMarqueePartners} hrefPrefix="/partners" />
        </section>
      </main>
      <LegalFooter />
    </div>
  );
}

function HuggingFaceIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12.025 1.13c-5.77 0-10.449 4.647-10.449 10.378 0 1.112.178 2.181.503 3.185.064-.222.203-.444.416-.577a.96.96 0 0 1 .524-.15c.293 0 .584.124.84.284.278.173.48.408.71.694.226.282.458.611.684.951v-.014c.017-.324.106-.622.264-.874s.403-.487.762-.543c.3-.047.596.06.787.203s.31.313.4.467c.15.257.212.468.233.542.01.026.653 1.552 1.657 2.54.616.605 1.01 1.223 1.082 1.912.055.537-.096 1.059-.38 1.572.637.121 1.294.187 1.967.187.657 0 1.298-.063 1.921-.178-.287-.517-.44-1.041-.384-1.581.07-.69.465-1.307 1.081-1.913 1.004-.987 1.647-2.513 1.657-2.539.021-.074.083-.285.233-.542.09-.154.208-.323.4-.467a1.08 1.08 0 0 1 .787-.203c.359.056.604.29.762.543s.247.55.265.874v.015c.225-.34.457-.67.683-.952.23-.286.432-.52.71-.694.257-.16.547-.284.84-.285a.97.97 0 0 1 .524.151c.228.143.373.388.43.625l.006.04a10.3 10.3 0 0 0 .534-3.273c0-5.731-4.678-10.378-10.449-10.378M8.327 6.583a1.5 1.5 0 0 1 .713.174 1.487 1.487 0 0 1 .617 2.013c-.183.343-.762-.214-1.102-.094-.38.134-.532.914-.917.71a1.487 1.487 0 0 1 .69-2.803m7.486 0a1.487 1.487 0 0 1 .689 2.803c-.385.204-.536-.576-.916-.71-.34-.12-.92.437-1.103.094a1.487 1.487 0 0 1 .617-2.013 1.5 1.5 0 0 1 .713-.174m-10.68 1.55a.96.96 0 1 1 0 1.921.96.96 0 0 1 0-1.92m13.838 0a.96.96 0 1 1 0 1.92.96.96 0 0 1 0-1.92M8.489 11.458c.588.01 1.965 1.157 3.572 1.164 1.607-.007 2.984-1.155 3.572-1.164.196-.003.305.12.305.454 0 .886-.424 2.328-1.563 3.202-.22-.756-1.396-1.366-1.63-1.32q-.011.001-.02.006l-.044.026-.01.008-.03.024q-.018.017-.035.036l-.032.04a1 1 0 0 0-.058.09l-.014.025q-.049.088-.11.19a1 1 0 0 1-.083.116 1.2 1.2 0 0 1-.173.18q-.035.029-.075.058a1.3 1.3 0 0 1-.251-.243 1 1 0 0 1-.076-.107c-.124-.193-.177-.363-.337-.444-.034-.016-.104-.008-.2.022q-.094.03-.216.087-.06.028-.125.063l-.13.074q-.067.04-.136.086a3 3 0 0 0-.135.096 3 3 0 0 0-.26.219 2 2 0 0 0-.12.121 2 2 0 0 0-.106.128l-.002.002a2 2 0 0 0-.09.132l-.001.001a1.2 1.2 0 0 0-.105.212q-.013.036-.024.073c-1.139-.875-1.563-2.317-1.563-3.203 0-.334.109-.457.305-.454m.836 10.354c.824-1.19.766-2.082-.365-3.194-1.13-1.112-1.789-2.738-1.789-2.738s-.246-.945-.806-.858-.97 1.499.202 2.362c1.173.864-.233 1.45-.685.64-.45-.812-1.683-2.896-2.322-3.295s-1.089-.175-.938.647 2.822 2.813 2.562 3.244-1.176-.506-1.176-.506-2.866-2.567-3.49-1.898.473 1.23 2.037 2.16c1.564.932 1.686 1.178 1.464 1.53s-3.675-2.511-4-1.297c-.323 1.214 3.524 1.567 3.287 2.405-.238.839-2.71-1.587-3.216-.642-.506.946 3.49 2.056 3.522 2.064 1.29.33 4.568 1.028 5.713-.624m5.349 0c-.824-1.19-.766-2.082.365-3.194 1.13-1.112 1.789-2.738 1.789-2.738s.246-.945.806-.858.97 1.499-.202 2.362c-1.173.864.233 1.45.685.64.451-.812 1.683-2.896 2.322-3.295s1.089-.175.938.647-2.822 2.813-2.562 3.244 1.176-.506 1.176-.506 2.866-2.567 3.49-1.898-.473 1.23-2.037 2.16c-1.564.932-1.686 1.178-1.464 1.53s3.675-2.511 4-1.297c.323 1.214-3.524 1.567-3.287 2.405.238.839 2.71-1.587 3.216-.642.506.946-3.49 2.056-3.522 2.064-1.29.33-4.568 1.028-5.713-.624" />
    </svg>
  );
}
