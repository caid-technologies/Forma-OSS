import type { ReactNode } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

export const PUBLIC_CARD_CLASS = "rounded-xl border border-[#2c2f37] bg-[#181b22]";
export const PUBLIC_BUTTON_OUTLINE_CLASS =
  "inline-flex h-8 items-center gap-1.5 rounded-lg border border-[#2c2f37] px-3 text-xs font-medium text-slate-300 transition hover:bg-white/5 hover:text-white";
export const PUBLIC_BUTTON_PRIMARY_CLASS =
  "inline-flex h-8 items-center gap-1.5 rounded-lg bg-white px-3 text-xs font-medium text-black transition hover:bg-slate-200";

export default function PublicAppShell({
  badge,
  title,
  homeHref = "/",
  homeLabel = "Home",
  children,
}: {
  badge: string;
  title: string;
  homeHref?: string;
  homeLabel?: string;
  children: ReactNode;
}) {
  return (
    <div className="min-h-screen bg-[#0f1117] font-sans text-zinc-100">
      <header className="workspace-chrome-header px-4 pb-5 pt-2">
        <div className="mx-auto flex w-full max-w-7xl items-center gap-3">
          <Link href={homeHref} className={PUBLIC_BUTTON_OUTLINE_CLASS}>
            <ArrowLeft className="h-3.5 w-3.5" />
            {homeLabel}
          </Link>
          <div className="flex min-w-0 items-center gap-2">
            <span className="inline-flex shrink-0 items-center rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
              {badge}
            </span>
            <h1 className="truncate text-sm font-semibold tracking-tight text-zinc-100">{title}</h1>
          </div>
        </div>
      </header>
      <div className="mx-auto w-full max-w-7xl px-4 py-5">{children}</div>
    </div>
  );
}
