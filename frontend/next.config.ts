import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    // Same relative /api path in dev and on Railway; no CORS.
    const backend = process.env.BACKEND_URL ?? "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
