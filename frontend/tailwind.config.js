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
        brand: {
          50: '#ecfeff',
          100: '#cffaff',
          200: '#a5f3fc',
          300: '#67e8f9',
          400: '#22d3ee',
          500: '#06b6d4',
          600: '#0891b2',
          700: '#0e7490',
          800: '#155e75',
          900: '#164e63',
          950: '#083344',
        },
        trade: {
          buy: '#10b981',
          sell: '#ef4444',
          wait: '#f59e0b',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        // Soft elevation for glass cards, and a focused cyan glow for accents.
        card: '0 1px 2px rgba(0,0,0,0.3), 0 8px 24px -12px rgba(0,0,0,0.5)',
        'card-hover': '0 1px 2px rgba(0,0,0,0.3), 0 16px 40px -16px rgba(0,0,0,0.6)',
        glow: '0 0 0 1px rgba(34,211,238,0.15), 0 8px 32px -8px rgba(34,211,238,0.35)',
        'glow-sm': '0 0 20px -6px rgba(34,211,238,0.5)',
      },
      backgroundImage: {
        'brand-gradient': 'linear-gradient(135deg, #22d3ee 0%, #3b82f6 100%)',
        'card-sheen': 'linear-gradient(180deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0) 100%)',
        'grid-faint':
          'linear-gradient(rgba(148,163,184,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.04) 1px, transparent 1px)',
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
      },
      animation: {
        'fade-in-up': 'fade-in-up 0.4s ease-out both',
        'fade-in': 'fade-in 0.5s ease-out both',
        shimmer: 'shimmer 1.6s infinite',
        float: 'float 6s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
