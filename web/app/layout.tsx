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
      <body>
        <style>{`
          /* Fintech design-panel density pass: preserve hierarchy, remove dead masthead space. */
          .shell { padding-top: 10px; }
          .topbar { min-height: 46px; padding: 2px 2px 10px; }
          .hero { padding: 24px 28px 24px; }
          .hero-grid { margin-top: 18px; gap: 30px; }
          .signal-subline { margin-top: 13px; }
          @media (max-width: 760px) {
            .shell { padding-top: 7px; }
            .topbar { min-height: 40px; padding: 0 2px 8px; }
            .hero { padding: 18px 17px; }
            .hero-grid { margin-top: 16px; gap: 18px; }
            .signal-subline { margin-top: 11px; }
          }
        `}</style>
        {children}
      </body>
    </html>
  );
}
