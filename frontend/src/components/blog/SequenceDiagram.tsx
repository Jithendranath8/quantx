import { useId } from 'react';

export interface SequenceParticipant {
  id: string;
  label: string;
  /** Short mono caption under the name, e.g. the module it lives in. */
  sub?: string;
}

export type SequenceStep =
  | {
      kind: 'msg';
      from: string;
      to: string;
      label: string;
      /** A response travelling back: drawn dashed and muted. */
      reply?: boolean;
      /** A call that only happens under a condition: drawn dashed in brand colour. */
      optional?: boolean;
    }
  | {
      kind: 'note';
      /** One participant, or the first and last of a span. */
      over: [string] | [string, string];
      text: string;
      tone?: 'gate' | 'loop';
    };

const PAD_X = 20;
const HEAD_TOP = 12;
const HEAD_H = 50;
const MSG_H = 38;
const SELF_H = 50;
const NOTE_H = 36;

/**
 * A small, data-driven UML sequence diagram rendered as SVG.
 *
 * Steps are drawn top to bottom in order; message labels are numbered so the
 * prose beside the diagram can refer to them. Text gets a dark halo
 * (paint-order: stroke) so it stays legible where it crosses a lifeline.
 */
export function SequenceDiagram({
  participants,
  steps,
  colWidth = 140,
  title,
}: {
  participants: SequenceParticipant[];
  steps: SequenceStep[];
  colWidth?: number;
  title: string;
}) {
  const uid = useId().replace(/:/g, '');
  const index = new Map(participants.map((p, i) => [p.id, i]));
  const x = (id: string) => PAD_X + colWidth * (index.get(id) ?? 0) + colWidth / 2;
  const width = PAD_X * 2 + colWidth * participants.length;

  let y = HEAD_TOP + HEAD_H + 30;
  let n = 0;
  const rows = steps.map((step) => {
    const top = y;
    if (step.kind === 'note') {
      y += NOTE_H + 8;
      return { step, top, num: 0 };
    }
    y += step.from === step.to ? SELF_H : MSG_H;
    n += 1;
    return { step, top, num: n };
  });
  const height = y + 12;

  const halo = { paintOrder: 'stroke', stroke: '#07080a', strokeWidth: 5, strokeLinejoin: 'round' } as const;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      role="img"
      aria-label={title}
      className="block font-sans"
      style={{ minWidth: Math.round(width * 0.82) }}
    >
      <title>{title}</title>
      <defs>
        <marker id={`${uid}-a`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" className="fill-zinc-300" />
        </marker>
        <marker id={`${uid}-r`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" className="fill-zinc-500" />
        </marker>
        <marker id={`${uid}-o`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" className="fill-brand-400" />
        </marker>
      </defs>

      {/* Lifelines */}
      {participants.map((p) => (
        <line
          key={`life-${p.id}`}
          x1={x(p.id)}
          x2={x(p.id)}
          y1={HEAD_TOP + HEAD_H}
          y2={height - 6}
          className="stroke-white/10"
          strokeDasharray="3 5"
        />
      ))}

      {/* Participant heads */}
      {participants.map((p) => (
        <g key={`head-${p.id}`}>
          <rect
            x={x(p.id) - colWidth / 2 + 8}
            y={HEAD_TOP}
            width={colWidth - 16}
            height={HEAD_H}
            rx={10}
            className="fill-ink-850 stroke-white/15"
          />
          <text x={x(p.id)} y={HEAD_TOP + (p.sub ? 22 : 30)} textAnchor="middle" className="fill-white text-[13px] font-medium">
            {p.label}
          </text>
          {p.sub && (
            <text x={x(p.id)} y={HEAD_TOP + 39} textAnchor="middle" className="fill-zinc-500 font-mono text-[10px]">
              {p.sub}
            </text>
          )}
        </g>
      ))}

      {rows.map(({ step, top, num }, i) => {
        if (step.kind === 'note') {
          const [a, b = a] = step.over;
          let left = Math.min(x(a), x(b)) - colWidth / 2 + 10;
          let right = Math.max(x(a), x(b)) + colWidth / 2 - 10;
          // Grow a note around its centre when its text is wider than the span
          // (≈6.4px per character at 12px), staying inside the drawing.
          const needed = step.text.length * 6.4 + 28;
          if (right - left < needed) {
            const centre = (left + right) / 2;
            left = Math.max(4, centre - needed / 2);
            right = Math.min(width - 4, left + needed);
          }
          const tone =
            step.tone === 'gate'
              ? 'fill-brand-500/10 stroke-brand-400/50'
              : step.tone === 'loop'
                ? 'fill-white/[0.03] stroke-white/20'
                : 'fill-ink-850 stroke-white/15';
          return (
            <g key={i}>
              <rect
                x={left}
                y={top}
                width={right - left}
                height={NOTE_H}
                rx={8}
                className={tone}
                strokeDasharray={step.tone === 'loop' ? '4 4' : undefined}
              />
              <text
                x={(left + right) / 2}
                y={top + NOTE_H / 2 + 4}
                textAnchor="middle"
                className={`text-[12px] ${step.tone === 'gate' ? 'fill-brand-200' : 'fill-zinc-300'}`}
              >
                {step.text}
              </text>
            </g>
          );
        }

        const x1 = x(step.from);
        const x2 = x(step.to);
        const lineClass = step.optional ? 'stroke-brand-400' : step.reply ? 'stroke-zinc-500' : 'stroke-zinc-300';
        const marker = step.optional ? `${uid}-o` : step.reply ? `${uid}-r` : `${uid}-a`;
        const dash = step.reply || step.optional ? '5 4' : undefined;
        const labelClass = step.reply ? 'fill-zinc-400' : 'fill-zinc-200';

        if (x1 === x2) {
          const ly = top + 14;
          return (
            <g key={i}>
              <path
                d={`M ${x1} ${ly} h 34 v 18 h -32`}
                fill="none"
                className={lineClass}
                strokeWidth={1.4}
                strokeDasharray={dash}
                markerEnd={`url(#${marker})`}
              />
              <text x={x1 + 42} y={ly + 13} className={`text-[12px] ${labelClass}`} style={halo}>
                <tspan className="fill-brand-400 font-mono">{num} </tspan>
                {step.label}
              </text>
            </g>
          );
        }

        const ly = top + 20;
        return (
          <g key={i}>
            <line
              x1={x1}
              x2={x2 + (x2 > x1 ? -2 : 2)}
              y1={ly}
              y2={ly}
              className={lineClass}
              strokeWidth={1.4}
              strokeDasharray={dash}
              markerEnd={`url(#${marker})`}
            />
            <text x={(x1 + x2) / 2} y={ly - 7} textAnchor="middle" className={`text-[12px] ${labelClass}`} style={halo}>
              <tspan className="fill-brand-400 font-mono">{num} </tspan>
              {step.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
