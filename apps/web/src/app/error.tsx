"use client";
import { ErrorState } from "@/components/ui";
export default function Page({ reset }: { reset: () => void }) {
  return <ErrorState error={new Error()} retry={reset} />;
}
