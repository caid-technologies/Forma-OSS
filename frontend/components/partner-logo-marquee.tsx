import Image from "next/image";
import Link from "next/link";

export type PartnerLogoItem = {
  name: string;
  slug: string;
  logo: string;
  logoSurface?: "dark" | "light";
  marqueeHref?: string | null;
};

type PartnerLogoMarqueeProps = {
  partners: PartnerLogoItem[];
  hrefPrefix?: string;
};

export default function PartnerLogoMarquee({ partners, hrefPrefix = "" }: PartnerLogoMarqueeProps) {
  const marqueeItems = Array.from({ length: 6 }, () => partners).flat();

  return (
    <div className="partner-logo-marquee overflow-hidden border-y border-[#2c2f37] bg-black/30 py-4" aria-label="Partner logos">
      <div className="partner-logo-track flex items-center gap-4">
        {marqueeItems.map((partner, index) => {
          const key = `${partner.slug}-${index}`;
          const lightSurface = partner.logoSurface === "light";
          const tileClassName = `inline-flex h-20 w-64 shrink-0 items-center justify-center border px-8 ${
            lightSurface
              ? "border-white/80 bg-white"
              : "border-[#2c2f37] bg-[#17181d]"
          }`;
          const logo = (
            <Image
              src={partner.logo}
              alt={`${partner.name} logo`}
              width={800}
              height={176}
              className="h-auto max-h-10 w-full object-contain"
              unoptimized
            />
          );

          if (partner.marqueeHref === null) {
            return (
              <div key={key} className={tileClassName} title={partner.name}>
                {logo}
              </div>
            );
          }

          return (
            <Link
              key={key}
              href={partner.marqueeHref || `${hrefPrefix}#${partner.slug}`}
              className={`${tileClassName} transition hover:border-cyan-300/60 hover:bg-[#1d2027] focus:outline-none focus:ring-2 focus:ring-cyan-300`}
              aria-label={`View ${partner.name} partner bio`}
              title={`View ${partner.name} partner bio`}
            >
              {logo}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
