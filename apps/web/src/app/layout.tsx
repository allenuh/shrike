import type { Metadata } from "next";
import { Suspense } from "react";
import { Shell } from "@/components/shell";
import { Loading } from "@/components/ui";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Shrike · Review intelligence", template: "%s · Shrike" },
  description:
    "A considered workspace for AI-assisted code reviews, findings, and repository activity.",
  robots: { index: false, follow: false },
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <Suspense fallback={<Loading />}>
          <Shell>{children}</Shell>
        </Suspense>
      </body>
    </html>
  );
}
