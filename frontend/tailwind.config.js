/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Outfit", "sans-serif"],
      },
      colors: {
        background: "#020617",
        card: "#0f172a",
        highlight: {
          from: "#6366f1",
          to: "#8b5cf6",
        },
      },
      backdropBlur: {
        glass: "14px",
      },
      boxShadow: {
        "glow-indigo": "0 0 24px -6px rgba(99, 102, 241, 0.45)",
        "glow-emerald": "0 0 24px -6px rgba(16, 185, 129, 0.45)",
        "glow-cyan": "0 0 24px -6px rgba(34, 211, 238, 0.45)",
      },
    },
  },
  plugins: [],
};
