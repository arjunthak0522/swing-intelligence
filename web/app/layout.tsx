import type { Metadata } from "next";
import "./globals.css";
import "./retail-overrides.css";

export const metadata: Metadata = {
  title: "RE-ENTRY",
  description: "Know when waiting stops helping."
};

// The unified dashboard owns decision freshness and market-phase labeling.
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
