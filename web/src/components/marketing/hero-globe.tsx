import { Icon } from "@/components/ui/icons";

const CURSOR = "M0 0 L0 46 L11.3 35.7 L19.3 52.9 L27.7 49.1 L20.2 32.3 L35.3 31.5Z";
const R = 150;
const MERIDIANS = [0, 1, 2, 3, 4, 5];

/**
 * The hero illustration: the WEB X-RAY globe browsing a site. Story loop (8 s):
 * a URL types into the address bar, the cursor clicks search, a scan sweeps the
 * globe and a finding is surfaced. Meridians turn continuously. Under reduced
 * motion it renders the final, static frame.
 */
export function HeroGlobe({
  className = "",
  showFinding = true,
  idPrefix = "hg",
}: {
  className?: string;
  showFinding?: boolean;
  idPrefix?: string;
}) {
  const id = (name: string) => `${idPrefix}-${name}`;
  return (
    <div className={`wx-hero relative aspect-square w-full ${className}`} aria-hidden>
      <svg viewBox="0 0 400 400" className="absolute inset-0 h-full w-full overflow-visible">
        <defs>
          <clipPath id={id("globe")}>
            <circle cx="200" cy="200" r={R - 2} />
          </clipPath>
          <mask id={id("bar")} maskUnits="userSpaceOnUse" x="0" y="0" width="400" height="400">
            <rect width="400" height="400" fill="#fff" />
            <rect x="20" y="164" width="360" height="72" rx="36" fill="#000" />
          </mask>
          <clipPath id={id("url")}>
            <rect className="url-reveal" x="82" y="182" width="226" height="36" />
          </clipPath>
          <linearGradient id={id("scan")} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="var(--wx-brand)" stopOpacity="0" />
            <stop offset="1" stopColor="var(--wx-brand)" stopOpacity="0.28" />
          </linearGradient>
        </defs>

        {/* soft ground shadow */}
        <ellipse cx="206" cy="372" rx="118" ry="12" fill="var(--wx-fg)" opacity="0.08" />

        {/* globe body */}
        <circle cx="200" cy="200" r={R} fill="var(--wx-surface)" />
        <g clipPath={`url(#${id("globe")})`}>
          {/* turned-side tint, like light catching the sphere */}
          <path d="M260 50 A150 150 0 0 1 260 350 A190 190 0 0 0 260 50Z" fill="var(--wx-brand)" opacity="0.14" />
          <g mask={`url(#${id("bar")})`} fill="none" stroke="var(--wx-fg)" strokeWidth="5" strokeLinecap="round">
            {MERIDIANS.map((i) => (
              <path
                key={i}
                className="meridian"
                d={`M200 ${200 - R} A${R} ${R} 0 0 1 200 ${200 + R}`}
                style={{ animationDelay: `${-i * 2}s` }}
              />
            ))}
            <path d="M200 50 V350" />
            <path d="M58 126 Q200 168 342 126" />
            <path d="M58 274 Q200 316 342 274" />
          </g>
          {/* scan sweep */}
          <g className="scan">
            <rect x="40" y="168" width="320" height="30" fill={`url(#${id("scan")})`} />
            <rect x="40" y="197" width="320" height="3" fill="var(--wx-brand)" />
          </g>
        </g>
        <circle cx="200" cy="200" r={R} fill="none" stroke="var(--wx-fg)" strokeWidth="6" />

        {/* defect hotspot surfaced by the scan */}
        <g className="hotspot">
          <circle cx="252" cy="284" r="15" fill="var(--wx-danger)" opacity="0.18" />
          <circle cx="252" cy="284" r="7" fill="var(--wx-danger)" stroke="var(--wx-surface)" strokeWidth="3" />
        </g>

        {/* address bar */}
        <rect x="24" y="168" width="352" height="64" rx="32" fill="var(--wx-surface)" stroke="var(--wx-fg)" strokeWidth="6" />
        <g transform="translate(52 188)" fill="none" stroke="var(--wx-fg-muted)" strokeWidth="2.6" strokeLinecap="round">
          <rect x="1" y="9" width="18" height="14" rx="3" />
          <path d="M5 9 V6 a5 5 0 0 1 10 0 V9" />
        </g>
        <g clipPath={`url(#${id("url")})`}>
          <text x="84" y="207" fontFamily="var(--font-mono)" fontSize="16" fill="var(--wx-fg)" letterSpacing="-0.4">
            northwind.test/checkout
          </text>
        </g>
        {/* search button */}
        <circle cx="334" cy="200" r="20" fill="var(--wx-brand)" />
        <g fill="none" stroke="var(--wx-brand-fg)" strokeWidth="3.2" strokeLinecap="round">
          <circle cx="331" cy="197" r="6.5" />
          <path d="M336 202 L342 208" />
        </g>
        <circle className="ripple" cx="334" cy="200" r="26" fill="none" stroke="var(--wx-brand)" strokeWidth="3" />

        {/* cursor */}
        <g className="cursor">
          <path d={CURSOR} transform="translate(290 330)" fill="var(--wx-brand)" stroke="var(--wx-fg)" strokeWidth="5" strokeLinejoin="round" />
        </g>
      </svg>

      {showFinding && (
        <div className="finding absolute right-0 top-[2%] w-[min(250px,66%)] sm:right-[-4%] rounded-[14px] border-[1.5px] border-fg bg-surface p-3.5 shadow-[4px_4px_0_var(--wx-fg)]">
          <div className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-danger">
            <span className="size-1.5 rounded-full bg-danger" /> Confirmed defect
          </div>
          <p className="mt-1.5 text-[13px] font-semibold leading-snug text-fg">&lsquo;Place order&rsquo; doesn&apos;t receive taps on mobile</p>
          <div className="mt-2 flex items-center gap-1.5 font-mono text-[10.5px] text-fg-muted">
            <Icon.Check size={11} className="text-success" /> 2/2 runs · test reproduced
          </div>
        </div>
      )}
    </div>
  );
}
