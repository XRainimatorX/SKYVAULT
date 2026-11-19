/**
 * Just enough Markdown for SKYVAULT's own reports: headings, bullets,
 * tables and paragraphs. Text is rendered as text, never as HTML.
 */
export default function Markdown({ text }: { text: string }) {
  const blocks: React.ReactNode[] = [];
  const lines = text.split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("# ")) {
      blocks.push(<h1 key={i}>{line.slice(2)}</h1>);
      i += 1;
    } else if (line.startsWith("## ")) {
      blocks.push(<h2 key={i}>{line.slice(3)}</h2>);
      i += 1;
    } else if (line.startsWith("- ")) {
      const items: string[] = [];
      while (i < lines.length && lines[i].startsWith("- ")) items.push(lines[i++].slice(2));
      blocks.push(
        <ul className="plain" key={i}>
          {items.map((item, n) => (
            <li key={n}>{item}</li>
          ))}
        </ul>,
      );
    } else if (line.startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].startsWith("|")) {
        const cells = lines[i++].split("|").slice(1, -1).map((c) => c.trim());
        if (!cells.every((c) => /^-+$/.test(c))) rows.push(cells);
      }
      const [head, ...body] = rows;
      blocks.push(
        <div className="table-wrap" key={i}>
          <table>
            <thead>
              <tr>
                {head.map((cell, n) => (
                  <th key={n}>{cell}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {body.map((row, r) => (
                <tr key={r}>
                  {row.map((cell, n) => (
                    <td key={n}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
    } else if (line.trim()) {
      blocks.push(<p key={i}>{line}</p>);
      i += 1;
    } else {
      i += 1;
    }
  }
  return <div className="markdown">{blocks}</div>;
}
