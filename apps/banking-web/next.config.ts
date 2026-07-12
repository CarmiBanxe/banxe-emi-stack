import type { NextConfig } from "next";

// SANDBOX: Banking Web — no live banking data; backend is LangGraph sandbox.
const nextConfig: NextConfig = {
  // Allow streaming responses from the sandbox LiteLLM/LangGraph backend.
  experimental: {
    serverActions: {
      allowedOrigins: ["localhost:3100"],
    },
  },
};

export default nextConfig;
