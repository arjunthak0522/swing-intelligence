import type { Metadata } from "next";
import FreshnessStatus from "./FreshnessStatus";
import HistoryTablePolish from "./HistoryTablePolish";
import "./globals.css";
import "./retail-overrides.css";
import "./premium-fintech.css";
import "./history-table-fix.css";

export const metadata: Metadata = {
  title: "RE-ENTRY",
  description: "Know when waiting stops helping."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <FreshnessStatus />
        <HistoryTablePolish />
        {children}
      </body>
    </html>
  );
}
