"use client";

import { useEffect } from "react";

function stripLeadingPlus(value: string | null) {
  if (!value) return value;
  return value.replace(/^\s*\+(?=\d)/, "");
}

function cleanPositiveRateSigns() {
  const selectors = [
    ".asset-performance-row > span:nth-child(4)",
    ".episode-asset-card > div:nth-of-type(3) strong",
    ".validation-detail-row > span:nth-child(6)",
  ];

  for (const selector of selectors) {
    document.querySelectorAll<HTMLElement>(selector).forEach((el) => {
      const cleaned = stripLeadingPlus(el.textContent);
      if (cleaned !== null && cleaned !== el.textContent) el.textContent = cleaned;
    });
  }

  document.querySelectorAll<HTMLElement>("span, small, dt").forEach((label) => {
    const text = (label.textContent || "").trim().toLowerCase();
    if (!text.includes("positive")) return;

    const parent = label.parentElement;
    if (!parent) return;
    parent.querySelectorAll<HTMLElement>("strong, b").forEach((value) => {
      const cleaned = stripLeadingPlus(value.textContent);
      if (cleaned !== null && cleaned !== value.textContent) value.textContent = cleaned;
    });
  });
}

export default function DashboardPolish() {
  useEffect(() => {
    cleanPositiveRateSigns();
    const observer = new MutationObserver(cleanPositiveRateSigns);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  return null;
}
