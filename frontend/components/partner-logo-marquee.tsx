import Image from "next/image";
import Link from "next/link";

export type PartnerLogoItem = {
  name: string;
  slug: string;
  logo: string;
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
        {marqueeItems.map((partner, index) => (
          <Link
            key={`${partner.slug}-${index}`}
            href={`${hrefPrefix}#${partner.slug}`}
            className="inline-flex h-20 w-64 shrink-0 items-center justify-center border border-[#2c2f37] bg-[#17181d] px-8 transition hover:border-cyan-300/60 hover:bg-[#1d2027] focus:outline-none focus:ring-2 focus:ring-cyan-300"
            aria-label={`View ${partner.name} partner bio`}
            title={`View ${partner.name} partner bio`}
          >
            <Image
              src={partner.logo}
              alt={`${partner.name} logo`}
              width={800}
              height={176}
              className="h-auto max-h-10 w-full object-contain"
              unoptimized
            />
          </Link>
        ))}
      </div>
    </div>
  );
}
