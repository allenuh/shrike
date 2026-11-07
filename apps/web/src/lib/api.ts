"use client";

import useSWR from "swr";
import { z } from "zod";

export class ApiError extends Error {
  constructor(public readonly status: number) {
    super(
      status === 401
        ? "Sign in to continue."
        : status === 404
          ? "This resource is unavailable."
          : "We couldn’t load this data. Please try again.",
    );
  }
}

export async function request<T>(
  path: string,
  schema: z.ZodType<T>,
): Promise<T> {
  const response = await fetch(`/api/backend/${path}`, {
    credentials: "same-origin",
    cache: "no-store",
    redirect: "error",
  });
  if (!response.ok) throw new ApiError(response.status);
  try {
    return schema.parse(await response.json());
  } catch {
    throw new ApiError(502);
  }
}

export function useApi<T>(path: string | null, schema: z.ZodType<T>) {
  return useSWR<T, ApiError>(path, (key: string) => request(key, schema), {
    shouldRetryOnError: false,
    revalidateOnFocus: false,
    dedupingInterval: 1500,
  });
}
