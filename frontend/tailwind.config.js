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
        bg: {
          base: "rgb(var(--tf-bg-base) / <alpha-value>)",
          surface: "rgb(var(--tf-bg-surface) / <alpha-value>)",
          card: "rgb(var(--tf-bg-card) / <alpha-value>)",
          hover: "rgb(var(--tf-bg-hover) / <alpha-value>)",
        },
        border: {
          DEFAULT: "rgb(var(--tf-border) / <alpha-value>)",
          subtle: "rgb(var(--tf-border-subtle) / <alpha-value>)",
        },
        text: {
          primary: "rgb(var(--tf-text-primary) / <alpha-value>)",
          secondary: "rgb(var(--tf-text-secondary) / <alpha-value>)",
          muted: "rgb(var(--tf-text-muted) / <alpha-value>)",
        },
        accent: {
          primary: "#6366f1",
          hover: "#4f46e5",
          success: "#22c55e",
          warning: "#f59e0b",
          danger: "#ef4444",
          info: "#3b82f6",
        },
        background: "rgb(var(--tf-bg-base) / <alpha-value>)",
        card: "rgb(var(--tf-bg-card) / <alpha-value>)",
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
