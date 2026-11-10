"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { currentRun, withRun } from "@/lib/api";

export const PAGES: [string, string][] = [
  ["/", "Overview"],
  ["/timeline/", "Timeline"],
  ["/replay/", "Replay"],
  ["/causal/", "Causal chain"],
  ["/failure/", "Failure map"],
  ["/compare/", "Compare"],
  ["/package/", "Result package"],
  ["/report/", "Briefing"],
];

export default function Nav() {
  const path = usePathname();
  // read after hydration: the static build cannot know the page's ?run=
  const [run, setRun] = useState("latest");
  useEffect(() => setRun(currentRun()), []);
  return (
    <nav aria-label="Pages">
      {PAGES.map(([href, label]) => (
        <a key={href} href={withRun(href, run)} aria-current={path === href ? "page" : undefined}>
          {label}
        </a>
      ))}
    </nav>
  );
}
