import daisyui from 'daisyui';

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Signal orange: a finance-terminal accent that stays clearly distinct
        // from the emerald/red reserved for P&L and the yellow used for warnings.
        brand: {
          50: '#fff6ed',
          100: '#ffead4',
          200: '#ffd1a8',
          300: '#ffb070',
          400: '#ff8f3d',
          500: '#ff7a1a',
          600: '#ef5e0b',
          700: '#c6450b',
          800: '#9d3711',
          900: '#7e3011',
          950: '#441506',
        },
        ink: {
          950: '#07080a',
          900: '#0c0d10',
          850: '#111216',
          800: '#16181d',
          700: '#1f2128',
        },
        trade: {
          buy: '#10b981',
          sell: '#ef4444',
          wait: '#f59e0b',
        },
      },
      fontFamily: {
        sans: ['Geist', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['"Instrument Serif"', 'ui-serif', 'Georgia', 'serif'],
        mono: ['"Geist Mono"', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        // Soft elevation for glass cards, and a focused brand glow for accents.
        card: '0 1px 2px rgba(0,0,0,0.3), 0 8px 24px -12px rgba(0,0,0,0.5)',
        'card-hover': '0 1px 2px rgba(0,0,0,0.3), 0 16px 40px -16px rgba(0,0,0,0.6)',
        glow: '0 0 0 1px rgba(255,122,26,0.18), 0 8px 32px -8px rgba(255,122,26,0.35)',
        'glow-sm': '0 0 20px -6px rgba(255,122,26,0.55)',
      },
      backgroundImage: {
        'brand-gradient': 'linear-gradient(135deg, #ffb070 0%, #ff7a1a 45%, #c6450b 100%)',
        'card-sheen': 'linear-gradient(180deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0) 100%)',
        'grid-faint':
          'linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px)',
      },
      keyframes: {
        'fade-in-up': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
        float: {
          '0%,100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' },
        },
        marquee: {
          from: { transform: 'translateX(0)' },
          to: { transform: 'translateX(calc(-50% - 0.5rem))' },
        },
        spotlight: {
          '0%': { opacity: '0', transform: 'translate(-72%, -62%) scale(0.5)' },
          '100%': { opacity: '1', transform: 'translate(-50%, -40%) scale(1)' },
        },
        beam: {
          '0%': { offsetDistance: '0%' },
          '100%': { offsetDistance: '100%' },
        },
      },
      animation: {
        'fade-in-up': 'fade-in-up 0.4s ease-out both',
        'fade-in': 'fade-in 0.5s ease-out both',
        shimmer: 'shimmer 1.6s infinite',
        float: 'float 6s ease-in-out infinite',
        marquee: 'marquee 40s linear infinite',
        spotlight: 'spotlight 2s ease 0.75s 1 forwards',
      },
    },
  },
  plugins: [daisyui],
  // DaisyUI is prefixed so its component classes (.card, .glass, .table…)
  // never collide with the app's own utilities; base styles stay ours.
  daisyui: {
    prefix: 'd-',
    base: false,
    logs: false,
    themes: [
      {
        quantx: {
          primary: '#ff7a1a',
          'primary-content': '#1a0a02',
          secondary: '#e4e4e7',
          accent: '#ffb070',
          neutral: '#16181d',
          'base-100': '#0c0d10',
          'base-200': '#111216',
          'base-300': '#1f2128',
          'base-content': '#e4e4e7',
          info: '#60a5fa',
          success: '#10b981',
          warning: '#facc15',
          error: '#ef4444',
          '--rounded-box': '1rem',
          '--rounded-btn': '0.6rem',
        },
      },
    ],
  },
}
