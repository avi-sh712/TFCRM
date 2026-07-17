import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

const storageKey = "talentforge_theme";

function initialTheme() {
  const saved = localStorage.getItem(storageKey);
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export default function ThemeToggle({ className = "" }) {
  const [theme, setTheme] = useState(initialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(storageKey, theme);
  }, [theme]);

  const isLight = theme === "light";
  return (
    <button
      type="button"
      onClick={() => setTheme(isLight ? "dark" : "light")}
      title={`Switch to ${isLight ? "dark" : "light"} theme`}
      aria-label={`Switch to ${isLight ? "dark" : "light"} theme`}
      className={`grid h-10 w-10 place-items-center rounded-lg border border-border bg-bg-card text-text-secondary hover:bg-bg-hover hover:text-text-primary ${className}`}
    >
      {isLight ? <Moon size={18} /> : <Sun size={18} />}
    </button>
  );
}
