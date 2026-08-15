import type { Metadata } from "next";
import localFont from "next/font/local";
import type { ReactNode } from "react";
import "./globals.css";

const seasonMix = localFont({
  src: [
    { path: "./fonts/SeasonMix-Regular.woff2", weight: "400" },
    { path: "./fonts/SeasonMix-Medium.woff2", weight: "500" },
  ],
  variable: "--font-season-mix",
  display: "swap",
});

const seasonSans = localFont({
  src: [
    { path: "./fonts/SeasonSans-Regular.woff2", weight: "400" },
    { path: "./fonts/SeasonSans-Medium.woff2", weight: "500" },
    { path: "./fonts/SeasonSans-Bold.woff2", weight: "700" },
  ],
  variable: "--font-season-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Future Coach",
    template: "%s · Future Coach",
  },
  description: "Grounded coaching, session planning, and member context.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en"
      className={`${seasonMix.variable} ${seasonSans.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        <template
          id="impeccable-direction-contract"
          data-seed="261a14bc"
          dangerouslySetInnerHTML={{
            __html:
              "<!-- THESIS: One member, one actionable morning signal, and one directly editable session; refuse the generic metric-card AI dashboard. OWN-WORLD: Future ink and warm off-white, Season Mix display, Season Sans UI, fine rules, light bounded surfaces, restrained peach/lilac/powder accents. STORY: Scan Jordan, celebrate the win, shape today's session, confirm it, and ask Copilot without leaving the workspace. FIRST VIEWPORT: Two thin shared header rows above a 69/31 Dashboard and persistent Copilot split; the session table dominates and Confirm session is the only dark action. FORM: Future Daily Signal canon, fourth direction card, seed 261a14bc. FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md -->",
          }}
        />
        {children}
      </body>
    </html>
  );
}
