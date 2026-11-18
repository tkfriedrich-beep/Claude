import type { Metadata, Viewport } from "next";
import "@fontsource-variable/instrument-sans/wght.css";
import "@fontsource-variable/newsreader/standard.css";
import "@fontsource-variable/newsreader/standard-italic.css";
import "@fontsource/ibm-plex-mono/latin-400.css";
import "@fontsource/ibm-plex-mono/latin-500.css";
import "./globals.css";
import { Providers } from "@/app/providers";
import { AppShell } from "@/components/cockpit/app-shell";

export const metadata: Metadata = {
  title: "OttoOS",
  description: "The operating system for judgment, orchestration, and execution — local-first.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f1ea" },
    { media: "(prefers-color-scheme: dark)", color: "#141310" },
  ],
};

// Midnight graphite is the default; parchment is the preserved alternative (spec §01).
const themeInit = `
try {
  var t = localStorage.getItem("cockpit-theme") || "dark";
  var r = t === "system" ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : t;
  document.documentElement.dataset.theme = r;
} catch (e) { document.documentElement.dataset.theme = "dark"; }
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      data-theme="dark"
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
      </head>
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
