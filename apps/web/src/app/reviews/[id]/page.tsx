import { notFound } from "next/navigation";
import { ReviewDetail } from "@/components/review-detail";
export const metadata = { title: "Review detail" };
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  if (!/^[a-f0-9-]{36}$/.test(id)) notFound();
  return <ReviewDetail id={id} />;
}
