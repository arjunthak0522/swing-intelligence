import type { WashoutSnapshot } from "../lib/reentry";
import CategorizedIndicatorBoard from "./CategorizedIndicatorBoard";

export default function LeadingIndicators({ washout }: { washout: WashoutSnapshot }) {
  return <CategorizedIndicatorBoard washout={washout} />;
}
