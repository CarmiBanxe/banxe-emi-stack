/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,jsx,ts,tsx}", "./components/**/*.{js,jsx,ts,tsx}"],
  presets: [require("nativewind/preset")],
  theme: {
    extend: {
      colors: {
        sandbox: {
          bg: "#fef3c7",
          border: "#f59e0b",
          text: "#92400e",
        },
        banxe: {
          primary: "#1e40af",
          secondary: "#3b82f6",
        },
      },
    },
  },
  plugins: [],
};
