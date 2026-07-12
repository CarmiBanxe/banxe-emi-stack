import type { Config } from "tailwindcss";
import typography from "@tailwindcss/typography";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        sandbox: {
          bg: "#fef3c7",
          border: "#f59e0b",
          text: "#92400e",
        },
      },
    },
  },
  plugins: [typography],
};

export default config;
