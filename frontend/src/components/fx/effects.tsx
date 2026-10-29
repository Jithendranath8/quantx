/**
 * Motion primitives in the spirit of Aceternity UI, written against our own
 * tokens so they share the app's palette rather than shipping a second one.
 */
import React, { useRef } from 'react';
import { motion, useInView, useMotionTemplate, useMotionValue } from 'motion/react';

/** Soft conic light sweeping in from the top-left of a hero. */
export function Spotlight({ className = '', fill = '#ff7a1a' }: { className?: string; fill?: string }) {
  return (
    <svg
      className={`pointer-events-none absolute z-0 h-[169%] w-[138%] opacity-0 animate-spotlight lg:w-[84%] ${className}`}
      viewBox="0 0 3787 2842"
      fill="none"
      aria-hidden="true"
    >
      <g filter="url(#spotlight-blur)">
        <ellipse
          cx="1924.71"
          cy="273.501"
          rx="1924.71"
          ry="273.501"
          transform="matrix(-0.822377 -0.568943 -0.568943 0.822377 3631.88 2291.09)"
          fill={fill}
          fillOpacity="0.16"
        />
      </g>
      <defs>
        <filter id="spotlight-blur" x="0.86" y="0.84" width="3785.16" height="2840.26" filterUnits="userSpaceOnUse" colorInterpolationFilters="sRGB">
          <feFlood floodOpacity="0" result="BackgroundImageFix" />
          <feBlend mode="normal" in="SourceGraphic" in2="BackgroundImageFix" result="shape" />
          <feGaussianBlur stdDeviation="151" result="effect1_foregroundBlur" />
        </filter>
      </defs>
    </svg>
  );
}

/** Hairline grid that fades out radially, used behind heroes and CTAs. */
export function GridBackdrop({ className = '' }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`pointer-events-none absolute inset-0 bg-grid-faint [background-size:56px_56px] [mask-image:radial-gradient(ellipse_at_center,black_20%,transparent_72%)] ${className}`}
    />
  );
}

/** Card whose border and surface light up under the cursor. */
export function SpotlightCard({
  children,
  className = '',
  radius = 360,
}: {
  children: React.ReactNode;
  className?: string;
  radius?: number;
}) {
  const x = useMotionValue(-radius);
  const y = useMotionValue(-radius);
  const glow = useMotionTemplate`radial-gradient(${radius}px circle at ${x}px ${y}px, rgba(255,122,26,0.12), transparent 70%)`;
  const ring = useMotionTemplate`radial-gradient(${radius * 0.6}px circle at ${x}px ${y}px, rgba(255,160,90,0.55), transparent 70%)`;

  return (
    <div
      onMouseMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        x.set(e.clientX - r.left);
        y.set(e.clientY - r.top);
      }}
      onMouseLeave={() => {
        x.set(-radius);
        y.set(-radius);
      }}
      className={`group relative rounded-3xl border border-white/[0.07] bg-ink-900/70 ${className}`}
    >
      {/* Border highlight: a masked layer that only shows on the 1px edge. */}
      <motion.div
        aria-hidden="true"
        className="pointer-events-none absolute -inset-px rounded-3xl opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        style={{
          background: ring,
          WebkitMask: 'linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0)',
          WebkitMaskComposite: 'xor',
          maskComposite: 'exclude',
          padding: 1,
        }}
      />
      <motion.div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 rounded-3xl opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        style={{ background: glow }}
      />
      <div className="relative">{children}</div>
    </div>
  );
}

/** Endless horizontal strip; pauses on hover so items stay readable. */
export function Marquee({ items, className = '' }: { items: React.ReactNode[]; className?: string }) {
  return (
    <div
      className={`group relative flex overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_12%,black_88%,transparent)] ${className}`}
    >
      {[0, 1].map((copy) => (
        <ul
          key={copy}
          aria-hidden={copy === 1}
          className="flex shrink-0 items-center gap-4 pr-4 animate-marquee group-hover:[animation-play-state:paused]"
        >
          {items.map((item, i) => (
            <li key={i} className="shrink-0">
              {item}
            </li>
          ))}
        </ul>
      ))}
    </div>
  );
}

/** Words fade and un-blur in sequence once scrolled into view. */
export function RevealWords({ text, className = '' }: { text: string; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: '-10% 0px' });
  return (
    <span ref={ref} className={className}>
      {text.split(' ').map((word, i) => (
        <motion.span
          key={`${word}-${i}`}
          className="inline-block"
          initial={{ opacity: 0, filter: 'blur(8px)', y: 6 }}
          animate={inView ? { opacity: 1, filter: 'blur(0px)', y: 0 } : undefined}
          transition={{ duration: 0.5, delay: i * 0.06, ease: 'easeOut' }}
        >
          {word}&nbsp;
        </motion.span>
      ))}
    </span>
  );
}

/** Fade-up wrapper for sections entering the viewport. */
export function Reveal({
  children,
  delay = 0,
  className = '',
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-8% 0px' }}
      transition={{ duration: 0.6, delay, ease: [0.21, 0.47, 0.32, 0.98] }}
    >
      {children}
    </motion.div>
  );
}

/** Primary CTA with a light that travels around its border. */
export function MovingBorderButton({
  children,
  className = '',
  as: Tag = 'span',
}: {
  children: React.ReactNode;
  className?: string;
  as?: 'span' | 'div';
}) {
  return (
    <Tag className={`relative inline-flex overflow-hidden rounded-full p-px ${className}`}>
      <span
        aria-hidden="true"
        className="absolute inset-[-1000%] animate-[spin_3.5s_linear_infinite] bg-[conic-gradient(from_90deg_at_50%_50%,#ff7a1a_0%,#16181d_35%,#ffd1a8_50%,#16181d_65%,#ff7a1a_100%)]"
      />
      <span className="relative inline-flex h-full w-full items-center justify-center gap-2 rounded-full bg-ink-950 px-6 py-3 text-sm font-medium text-white backdrop-blur-3xl transition-colors group-hover:bg-ink-900">
        {children}
      </span>
    </Tag>
  );
}
