"use client";

import { usePathname } from "next/navigation";

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
  return (
    <nav aria-label="Pages">
      {PAGES.map(([href, label]) => (
        <a key={href} href={href} aria-current={path === href ? "page" : undefined}>
          {label}
        </a>
      ))}
    </nav>
  );
}
