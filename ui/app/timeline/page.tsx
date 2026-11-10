"use client";

import Status from "@/components/Status";
import { type Timeline, runApi, useApi } from "@/lib/api";

export default function TimelinePage() {
  const loaded = useApi<Timeline>(runApi("timeline"));
  return (
    <>
      <h1>Timeline</h1>
      <p className="lede">Every tick in order: what each unit chose, what happened, who was destroyed.</p>
      <Status loaded={loaded}>
        {(timeline) => (
          <>
            {timeline.ticks.map((tick) => {
              const destroyed = new Set(
                tick.destroyed.map((loss) => `${loss.name} in the`),
              );
              return (
                <section className="panel tick" key={tick.tick} id={`tick-${tick.tick}`}>
                  <h3>
                    Tick {tick.tick}
                    {tick.destroyed.length > 0 && (
                      <span className="muted">
                        {" "}
                        — {tick.destroyed.map((loss) => `${loss.name} destroyed by ${loss.by_name}`).join("; ")}
                      </span>
                    )}
                  </h3>
                  <ul className="plain">
                    {tick.lines.map((line, index) => (
                      <li
                        key={index}
                        className={[...destroyed].some((start) => line.startsWith(start)) ? "destroyed" : undefined}
                      >
                        {line}
                      </li>
                    ))}
                  </ul>
                </section>
              );
            })}
          </>
        )}
      </Status>
    </>
  );
}
