/** @type {import('tailwindcss').Config} */

// Every scale reads CSS variables defined in src/index.css, so light and dark
// themes share one set of class names.
const STEPS = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900];
const scale = (name) =>
  Object.fromEntries(STEPS.map((step) => [step, `rgb(var(--c-${name}-${step}) / <alpha-value>)`]));
const token = (name) => `rgb(var(--c-${name}) / <alpha-value>)`;

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        slate: scale('slate'),
        brand: scale('brand'),
        rose: scale('rose'),
        amber: scale('amber'),
        emerald: scale('emerald'),
        indigo: scale('indigo'),
        teal: scale('teal'),
        orange: scale('orange'),
        fuchsia: scale('fuchsia'),
        canvas: token('canvas'),
        surface: token('surface'),
        sunken: token('sunken'),
        overlay: token('overlay'),
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      borderRadius: {
        xl: '0.875rem',
        '2xl': '1.125rem',
      },
      boxShadow: {
        sm: 'var(--shadow-sm)',
        DEFAULT: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
        xl: 'var(--shadow-xl)',
      },
      keyframes: {
        fadeIn: { from: { opacity: '0', transform: 'translateY(4px)' }, to: { opacity: '1', transform: 'translateY(0)' } },
        slideIn: { from: { transform: 'translateX(-100%)' }, to: { transform: 'translateX(0)' } },
        slideInRight: { from: { transform: 'translateX(100%)' }, to: { transform: 'translateX(0)' } },
        popIn: { from: { opacity: '0', transform: 'scale(0.97)' }, to: { opacity: '1', transform: 'scale(1)' } },
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-out both',
        'slide-in': 'slideIn 0.2s ease-out both',
        'slide-in-right': 'slideInRight 0.2s ease-out both',
        'pop-in': 'popIn 0.16s ease-out both',
      },
    },
  },
  plugins: [],
};
