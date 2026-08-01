import Image from "next/image";

type CaidLogoProps = {
  className?: string;
  sizes?: string;
};

export default function CaidLogo({ className = "h-5 w-9", sizes = "44px" }: CaidLogoProps) {
  return (
    <span className={`relative inline-block shrink-0 overflow-hidden align-middle ${className}`} aria-hidden="true">
      <Image
        src="/brand/caid-dark-logo-cropped.png"
        alt=""
        fill
        sizes={sizes}
        className="caid-logo-on-dark object-contain"
        unoptimized
      />
      <Image
        src="/brand/caid-logo.jpg"
        alt=""
        fill
        sizes={sizes}
        className="caid-logo-on-light object-cover"
        unoptimized
      />
    </span>
  );
}
