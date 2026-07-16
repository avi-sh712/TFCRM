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
        bg: { base: "#0a0b0f", surface: "#111318", card: "#161920", hover: "#1e2028" },
        border: { DEFAULT: "#2a2d38", subtle: "#1e2028" },
        text: { primary: "#f0f2f7", secondary: "#8b91a8", muted: "#555b72" },
        accent: { primary: "#6366f1", hover: "#4f46e5", success: "#22c55e", warning: "#f59e0b", danger: "#ef4444", info: "#3b82f6" },
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
