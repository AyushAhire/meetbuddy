"use client";

import { useState } from "react";
import { Copy, Check } from "lucide-react";

export function CopyTokenButton({ token }: { token: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(token);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <button
      onClick={copy}
      className="flex items-center gap-1.5 text-xs px-2 py-1 rounded border hover:bg-accent transition-colors"
      title="Copy API token for the browser extension"
    >
      {copied ? <Check className="w-3.5 h-3.5 text-green-600" /> : <Copy className="w-3.5 h-3.5" />}
      {copied ? "Copied!" : "Copy token"}
    </button>
  );
}
