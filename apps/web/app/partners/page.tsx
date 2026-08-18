import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { ArrowUpRight, Handshake } from "lucide-react";
import PublicAppShell, {
  PUBLIC_BUTTON_PRIMARY_CLASS,
  PUBLIC_CARD_CLASS,
} from "../../components/public-app-shell";
import { aboutMarqueePartners, partners } from "../../lib/partners";

export const metadata: Metadata = {
  title: "Partners | Forma",
  description: "Forma partners and infrastructure collaborators.",
};

export default function PartnersPage() {
  return (
    <PublicAppShell
      badge="General"
      title="Partners"
      homeHref="/about"
      homeLabel="About"
    >
      <div className="space-y-5 pb-4">
        {partners.map((partner) => (
          <article key={partner.slug} id={partner.slug} className={PUBLIC_CARD_CLASS}>
            <div className="flex flex-col gap-4 border-b border-[#2c2f37] px-5 py-4 xl:flex-row xl:items-start xl:justify-between">
              <div className="min-w-0">
                <p className="text-xs text-slate-500">AI infrastructure</p>
                <h2 className="mt-1 text-lg font-semibold tracking-tight text-white">{partner.name}</h2>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">{partner.summary}</p>
              </div>
              <Link
                href={partner.href}
                target="_blank"
                rel="noreferrer"
                className={PUBLIC_BUTTON_PRIMARY_CLASS}
              >
                Start with {partner.name}
                <ArrowUpRight className="h-3.5 w-3.5" />
              </Link>
            </div>
            <div className="grid gap-3 p-5 md:grid-cols-[220px_minmax(0,1fr)]">
              <div className="flex h-28 items-center justify-center rounded-xl border border-[#2c2f37] bg-[#002b36] px-6">
                <Image
                  src={partner.logo}
                  alt={`${partner.name} logo`}
                  width={800}
                  height={176}
                  className="h-auto max-h-10 w-full object-contain"
                  unoptimized
                  priority
                />
              </div>
              <p className="text-sm leading-6 text-slate-400">{partner.relationship}</p>
            </div>
          </article>
        ))}

        <article className={PUBLIC_CARD_CLASS}>
          <div className="border-b border-[#2c2f37] px-5 py-4">
            <div className="flex items-center gap-2">
              <Handshake className="h-4 w-4 text-emerald-400" />
              <h2 className="text-lg font-semibold tracking-tight text-white">Network</h2>
            </div>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
              Program and research partners around Forma.
            </p>
          </div>
          <div className="grid gap-3 p-5 sm:grid-cols-2 xl:grid-cols-4">
            {aboutMarqueePartners.map((partner) => {
              const lightSurface = partner.logoSurface === "light";
              return (
                <div
                  key={partner.slug}
                  className={`flex h-20 items-center justify-center rounded-xl border border-[#2c2f37] px-6 ${
                    lightSurface ? "bg-white" : "bg-[#002b36]"
                  }`}
                  title={partner.name}
                >
                  <Image
                    src={partner.logo}
                    alt={`${partner.name} logo`}
                    width={800}
                    height={176}
                    className="h-auto max-h-10 w-full object-contain"
                    unoptimized
                  />
                </div>
              );
            })}
          </div>
        </article>
      </div>
    </PublicAppShell>
  );
}
