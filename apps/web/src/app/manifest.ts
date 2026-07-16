import type { MetadataRoute } from "next";

// PWA manifest: "Add to Home Screen" installs Otto with the champagne-orb icon and the
// midnight-graphite chrome, opening standalone (no browser bars). Next.js auto-links this at
// /manifest.webmanifest, and app/apple-icon.png + app/icon.png supply the iOS/favicon icons.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "OttoOS",
    short_name: "Otto",
    description: "The operating system for judgment, orchestration, and execution — local-first.",
    start_url: "/",
    display: "standalone",
    background_color: "#141310",
    theme_color: "#141310",
    icons: [
      { src: "/icons/otto-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/otto-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/otto-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
