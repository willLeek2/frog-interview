/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#f1f7ff',
          100: '#e0f0ff',
          200: '#b8deff',
          300: '#7fc5ff',
          400: '#3ca9ff',
          500: '#008dff',
          600: '#0074db',
          700: '#005db1',
          800: '#004f90',
          900: '#064275',
        },
      },
      boxShadow: {
        soft: '0 12px 30px -12px rgba(0, 116, 219, 0.35)',
      },
    },
  },
  plugins: [],
}
