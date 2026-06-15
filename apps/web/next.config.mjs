/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static SPA — exported to ./out and served by the local FastAPI backend.
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
