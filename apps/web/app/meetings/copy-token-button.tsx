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
    <button onClick={copy} className="btn-ghost" title="Copy API token for the browser extension">
      {copied ? <Check className="w-3 h-3 text-green-500" /> : <Copy className="w-3 h-3" />}
      {copied ? "Copied" : "Copy token"}
    </button>
  );
}
