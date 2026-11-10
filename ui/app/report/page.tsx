"use client";

import { useEffect, useState } from "react";
import Markdown from "@/components/Markdown";
import { runApi } from "@/lib/api";

export default function ReportPage() {
  const [text, setText] = useState<string | null>(null);
  const [base, setBase] = useState("/api/runs/latest/");
  useEffect(() => {
    setBase(runApi(""));
    fetch(runApi("report.md"))
      .then((response) => (response.ok ? response.text() : Promise.reject(response.statusText)))
      .then(setText)
      .catch(() => setText(""));
  }, []);

  return (
    <>
      <h1>Briefing</h1>
      <p className="lede">The run, its failure exploration and its comparison, ready to take into a meeting.</p>
      <div className="controls">
        <a className="button" href={`${base}report.pdf`} download>
          Download PDF
        </a>
        <a className="button" href={`${base}report.docx`} download>
          Download Word
        </a>
        <a className="button" href={`${base}report.md`} download>
          Download Markdown
        </a>
      </div>
      <section className="panel">
        {text === null ? <p className="muted">Loading…</p> : <Markdown text={text} />}
      </section>
    </>
  );
}
