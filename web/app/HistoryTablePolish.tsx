"use client";

import { useEffect } from "react";

export default function HistoryTablePolish() {
  useEffect(() => {
    const polish = () => {
      document.querySelectorAll<HTMLElement>(".historical-evidence-card .period-cell small").forEach((node) => {
        const text = node.textContent ?? "";
        if (text.startsWith("to ")) node.textContent = `→ ${text.slice(3)}`;
      });
    };

    polish();
    const observer = new MutationObserver(polish);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  return null;
}
