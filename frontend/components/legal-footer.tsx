import Link from "next/link";
import { legalContactEmail, legalDocuments, legalEntityName } from "../lib/legal-docs";

const primaryFooterLinks = legalDocuments.filter((document) =>
  [
    "terms-of-service",
    "privacy-policy",
    "acceptable-use-policy",
    "hardware-safety-disclaimer",
    "cookie-and-local-storage-notice",
  ].includes(document.slug)
);

const secondaryFooterLinks = legalDocuments.filter((document) =>
  ["copyright-dmca-policy", "security-policy", "accessibility-statement"].includes(document.slug)
);

export default function LegalFooter() {
  return (
    <footer className="border-t border-[#292b31] bg-[#111216] px-5 py-8 font-sans text-slate-400">
      <div className="mx-auto grid w-full max-w-6xl gap-6 md:grid-cols-[1fr_2fr]">
        <div>
          <Link href="/" className="text-sm font-black uppercase tracking-[0.22em] text-white">
            Forma
          </Link>
          <p className="mt-3 max-w-sm text-xs leading-5 text-slate-500">
            {legalEntityName}
          </p>
          <a
            href={`mailto:${legalContactEmail}`}
            className="mt-2 inline-block text-xs text-slate-400 hover:text-white"
          >
            {legalContactEmail}
          </a>
        </div>

        <nav className="grid gap-4 text-xs sm:grid-cols-2" aria-label="Legal">
          <div className="flex flex-wrap gap-x-4 gap-y-2">
            {primaryFooterLinks.map((document) => (
              <Link key={document.slug} href={`/legal/${document.slug}`} className="hover:text-white">
                {document.title}
              </Link>
            ))}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-2 sm:justify-end">
            <Link href="/legal" className="hover:text-white">
              Legal
            </Link>
            {secondaryFooterLinks.map((document) => (
              <Link key={document.slug} href={`/legal/${document.slug}`} className="hover:text-white">
                {document.title}
              </Link>
            ))}
          </div>
        </nav>
      </div>
    </footer>
  );
}
