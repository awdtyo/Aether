/** Minimal markdown subset renderer (headers, bold, bullets, paragraphs).
 *  No dependencies; React escapes text by construction. */
import React from 'react';

function inline(text: string, keyPrefix: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**') && p.length > 4) {
      return <strong key={`${keyPrefix}-${i}`}>{p.slice(2, -2)}</strong>;
    }
    return <React.Fragment key={`${keyPrefix}-${i}`}>{p}</React.Fragment>;
  });
}

export function Markdown({ text }: { text: string }) {
  const lines = text.replace(/\\n/g, '\n').split('\n');
  const blocks: React.ReactNode[] = [];
  let bullets: string[] = [];

  const flushBullets = (key: number) => {
    if (bullets.length) {
      blocks.push(
        <ul key={`ul-${key}`}>
          {bullets.map((b, j) => <li key={j}>{inline(b, `li-${key}-${j}`)}</li>)}
        </ul>
      );
      bullets = [];
    }
  };

  lines.forEach((raw, i) => {
    const line = raw.trim();
    if (/^([-*])\s+/.test(line)) {
      bullets.push(line.replace(/^([-*])\s+/, ''));
      return;
    }
    flushBullets(i);
    if (!line) return;
    const h = line.match(/^(#{1,3})\s+(.*)/);
    if (h) {
      const level = h[1].length;
      const content = inline(h[2], `h-${i}`);
      blocks.push(
        level === 1 ? <h3 key={i}>{content}</h3>
        : level === 2 ? <h4 key={i}>{content}</h4>
        : <strong key={i} className="md-section">{content}</strong>
      );
      return;
    }
    const section = line.match(/^\*\*(.+)\*\*$/);
    if (section) {
      blocks.push(<div key={i} className="md-section">{section[1]}</div>);
      return;
    }
    blocks.push(<p key={i}>{inline(line, `p-${i}`)}</p>);
  });
  flushBullets(lines.length);

  return <div className="md">{blocks}</div>;
}
