/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "#0b0d12",
        card: "#0f1117",
        foreground: "#e8ecf5",
        muted: "#9aa2b1",
        primary: "#4f7dff",
        destructive: "#f87171",
      },
      borderRadius: {
        lg: "14px",
      },
    },
  },
  plugins: [],
};
