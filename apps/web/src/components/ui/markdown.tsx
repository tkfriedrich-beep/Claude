// Minimal renderer for cockpit-generated Markdown (headings, lists, tables, bold,
// code, links). Our own skills produce this content; it is still escaped fully.
import { Fragment } from "react";

function escapeHtml(text: string): string {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function inline(text: string): string {
  let safe = escapeHtml(text);
  safe = safe.replace(/`([^`]+)`/g, '<code class="rounded bg-line/50 px-1 font-mono text-[0.85em]">$1</code>');
  safe = safe.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  safe = safe.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  safe = safe.replace(/_([^_]+)_/g, "<em>$1</em>");
  return safe;
}

export function Markdown({ content }: { content: string }) {
  const lines = content.split("\n");
  const blocks: React.ReactNode[] = [];
  let list: string[] = [];
  let table: string[] = [];
  let quote: string[] = [];

  const flushList = (key: number) => {
    if (list.length) {
      blocks.push(
        <ul key={`ul${key}`} className="my-2 list-disc space-y-1 pl-5 text-sm">
          {list.map((item, i) => (
            <li key={i} dangerouslySetInnerHTML={{ __html: inline(item) }} />
          ))}
        </ul>,
      );
      list = [];
    }
  };
  const flushTable = (key: number) => {
    if (table.length >= 2) {
      const rows = table.filter((row) => !/^\|[\s\-|]+\|$/.test(row));
      const cells = rows.map((row) => row.split("|").slice(1, -1).map((c) => c.trim()));
      blocks.push(
        <div key={`tbl${key}`} className="my-3 overflow-x-auto">
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr>
                {cells[0]?.map((cell, i) => (
                  <th key={i} className="border-b border-line px-2 py-1.5 text-left font-semibold"
                      dangerouslySetInnerHTML={{ __html: inline(cell) }} />
                ))}
              </tr>
            </thead>
            <tbody>
              {cells.slice(1).map((row, ri) => (
                <tr key={ri}>
                  {row.map((cell, ci) => (
                    <td key={ci} className="border-b border-line/60 px-2 py-1.5"
                        dangerouslySetInnerHTML={{ __html: inline(cell) }} />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
    }
    table = [];
  };
  const flushQuote = (key: number) => {
    if (quote.length) {
      blocks.push(
        <blockquote key={`q${key}`}
          className="my-2 border-l-2 border-warn bg-warn-soft/50 px-3 py-2 text-[13px] rounded-r-lg"
          dangerouslySetInnerHTML={{ __html: inline(quote.join(" ")) }} />,
      );
      quote = [];
    }
  };

  lines.forEach((line, index) => {
    if (/^\|.*\|$/.test(line)) {
      flushList(index);
      table.push(line);
      return;
    }
    flushTable(index);
    if (/^\s*[-*] /.test(line)) {
      flushQuote(index);
      list.push(line.replace(/^\s*[-*] /, ""));
      return;
    }
    flushList(index);
    if (/^> ?/.test(line)) {
      quote.push(line.replace(/^> ?/, ""));
      return;
    }
    flushQuote(index);
    const heading = line.match(/^(#{1,4}) (.+)$/);
    if (heading) {
      const level = heading[1].length;
      const sizes = ["text-lg font-bold mt-4 mb-1", "text-base font-semibold mt-4 mb-1",
                     "text-[15px] font-semibold mt-3 mb-0.5", "text-sm font-semibold mt-2"];
      blocks.push(
        <div key={index} className={sizes[level - 1]}
             role="heading" aria-level={level + 1}
             dangerouslySetInnerHTML={{ __html: inline(heading[2]) }} />,
      );
      return;
    }
    if (line.trim() === "") {
      blocks.push(<Fragment key={index} />);
      return;
    }
    blocks.push(
      <p key={index} className="my-1.5 text-sm leading-relaxed"
         dangerouslySetInnerHTML={{ __html: inline(line) }} />,
    );
  });
  flushList(lines.length);
  flushTable(lines.length + 1);
  flushQuote(lines.length + 2);

  return <div className="max-w-none">{blocks}</div>;
}
