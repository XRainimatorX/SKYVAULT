"use client";

import type { Loaded } from "@/lib/api";

/** Renders children once loaded; otherwise says what is going on, in words. */
export default function Status<T>({ loaded, children }: {
  loaded: Loaded<T>;
  children: (data: T) => React.ReactNode;
}) {
  if (loaded.state === "loading") return <p className="muted">Loading…</p>;
  if (loaded.state === "missing")
    return (
      <div className="notice" role="status">
        <strong>Not in this workspace.</strong> {loaded.message}
      </div>
    );
  if (loaded.state === "error")
    return (
      <div className="notice error" role="alert">
        <strong>Could not load.</strong> {loaded.message}
      </div>
    );
  return <>{children(loaded.data)}</>;
}
