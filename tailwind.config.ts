import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        cw: {
          bg: "var(--cw-bg)",
          surface: "var(--cw-surface)",
          elevated: "var(--cw-elevated)",
          border: "var(--cw-border)",
          text: "var(--cw-text)",
          muted: "var(--cw-muted)",
          primary: "var(--cw-primary)",
          "primary-hover": "var(--cw-primary-hover)",
          secondary: "var(--cw-secondary)",
          accent: "var(--cw-accent)",
          success: "var(--cw-success)",
          warning: "var(--cw-warning)",
          danger: "var(--cw-danger)",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      boxShadow: {
        glass: "0 8px 32px 0 rgba(0, 0, 0, 0.37)",
        card: "0 4px 20px -2px rgba(0, 0, 0, 0.5)",
        glow: "0 0 25px -5px rgba(59, 130, 246, 0.4)",
      },
    },
  },
  plugins: [],
};

export default config;
