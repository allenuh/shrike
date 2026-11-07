"use client";

import { useSyncExternalStore } from "react";

function readDensity(): string {
  try {
    return window.localStorage.getItem("shrike-density") === "compact"
      ? "compact"
      : "comfortable";
  } catch {
    return "comfortable";
  }
}
function subscribe(listener: () => void) {
  window.addEventListener("storage", listener);
  window.addEventListener("shrike-preferences", listener);
  return () => {
    window.removeEventListener("storage", listener);
    window.removeEventListener("shrike-preferences", listener);
  };
}
export function useDensity() {
  return useSyncExternalStore(subscribe, readDensity, () => "comfortable");
}
export function saveDensity(value: string) {
  window.localStorage.setItem("shrike-density", value);
  window.dispatchEvent(new Event("shrike-preferences"));
}
