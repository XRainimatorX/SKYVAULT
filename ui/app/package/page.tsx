"use client";

import Status from "@/components/Status";
import { type PackageView, useApi } from "@/lib/api";

export default function PackagePage() {
  const loaded = useApi<PackageView>("/api/package");
  return (
    <>
      <h1>Result package</h1>
      <p className="lede">
        Everything one run produced, part by part. Open a part to see the data exactly as recorded.
      </p>
      <Status loaded={loaded}>
        {(view) => (
          <>
            {view.sections.map((section) => (
              <section className="panel" key={section.key} style={{ marginBottom: 10 }}>
                <details>
                  <summary>
                    <strong>{section.label}</strong> <span className="muted">— {section.summary}</span>
                  </summary>
                  <pre>{JSON.stringify(section.raw, null, 2)}</pre>
                </details>
              </section>
            ))}
          </>
        )}
      </Status>
    </>
  );
}
