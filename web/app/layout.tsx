import type { Metadata, Viewport } from "next";
import "./globals.css";
import "./retail-overrides.css";
import "./commercial.css";

export const metadata: Metadata = {
  title: "BTFD",
  description: "Know when the dip is worth buying.",
  appleWebApp: {
    capable: true,
    title: "BTFD",
    statusBarStyle: "default",
  },
  formatDetection: {
    telephone: false,
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#f7f6f2",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <style>{`
          .shell { padding-top: 10px; }
          .topbar { min-height: 46px; padding: 2px 2px 10px; }
          .hero { padding: 24px 28px 24px; }
          .hero-grid { margin-top: 18px; gap: 30px; }
          .signal-subline { margin-top: 13px; }
          @media (max-width: 760px) {
            .shell { padding-top: max(7px, env(safe-area-inset-top)); }
            .topbar { min-height: 44px; padding: 0 max(2px, env(safe-area-inset-right)) 8px max(2px, env(safe-area-inset-left)); }
            .hero { padding: 18px max(17px, env(safe-area-inset-right)) 18px max(17px, env(safe-area-inset-left)); }
            .hero-grid { margin-top: 16px; gap: 18px; }
            .signal-subline { margin-top: 11px; }
          }
        `}</style>
        {children}
      </body>
    </html>
  );
}
