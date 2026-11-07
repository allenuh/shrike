import Link from "next/link";
export default function Page() {
  return (
    <div className="state-card">
      <span className="eyebrow">404 · UNAVAILABLE</span>
      <h1>This page isn’t here.</h1>
      <p>The resource may have moved, or your account may not have access.</p>
      <Link href="/reviews" className="button">
        Back to reviews
      </Link>
    </div>
  );
}
