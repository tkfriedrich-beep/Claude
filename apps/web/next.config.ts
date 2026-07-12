import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // The UI never imports provider/connector SDKs (architecture invariant 1);
  // it talks only to the control plane at NEXT_PUBLIC_API_URL.
};

export default nextConfig;
