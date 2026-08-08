import type { NextConfig } from "next";

const apiProxyTarget = process.env.API_PROXY_TARGET || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: __dirname,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiProxyTarget}/api/:path*`,
      },
      {
        source: "/storage/:path*",
        destination: `${apiProxyTarget}/storage/:path*`,
      },
      {
        source: "/sample_images/:path*",
        destination: `${apiProxyTarget}/sample_images/:path*`,
      },
    ];
  },
};

export default nextConfig;
