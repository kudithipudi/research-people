/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/templates/**/*.html"],
  theme: {
    extend: {
      colors: {
        void: "#0A0C10",
        panel: "#12151B",
        panel2: "#171B22",
        line: "#232833",
        line2: "#323847",
        ink: "#ECEEF2",
        inkdim: "#97A0AF",
        inkfaint: "#5F6674",
        signal: "#45E6AC",
        signaldim: "#16332A",
        amber: "#F2BB4E",
        amberdim: "#3A2E14",
        alert: "#FF6E63",
        alertdim: "#3A1C19",
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      keyframes: {
        sweep: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(600%)" },
        },
        blink: {
          "0%, 100%": { opacity: 1 },
          "50%": { opacity: 0.25 },
        },
      },
      animation: {
        sweep: "sweep 1.8s linear infinite",
        blink: "blink 1.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
