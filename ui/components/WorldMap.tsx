"use client";

import type { Frame, Space, Unit } from "@/lib/api";

const CELL = 44;

/** Faction colours: the first two get fixed colours, others fall back to grey. */
export function factionColor(faction: string): string {
  if (faction === "RED") return "var(--red)";
  if (faction === "BLUE") return "var(--blue)";
  return "var(--muted)";
}

function place(space: Space, unit: Unit): [number, number] | null {
  if (unit.position === null) return null;
  if (space.type === "grid") {
    if (typeof unit.position === "string") return null;
    const [x, y] = unit.position;
    return [x * CELL + CELL / 2, y * CELL + CELL / 2];
  }
  const node = space.nodes.find((n) => n.id === unit.position);
  return node ? [(node.x + 1.2) * 200, (node.y + 1.2) * 200] : null;
}

/** The world at one frame: the space, every unit placed, its hp as a bar. */
export default function WorldMap({ space, frame }: { space: Space; frame: Frame }) {
  const width = space.type === "grid" ? space.width * CELL : 480;
  const height = space.type === "grid" ? space.height * CELL : 480;
  // Several units on one spot are fanned out so each stays visible
  const seen = new Map<string, number>();

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="world-map"
      data-tick={frame.tick}
      role="img"
      aria-label={`World at tick ${frame.tick}`}
    >
      {space.type === "grid" ? (
        Array.from({ length: space.width * space.height }, (_, i) => (
          <rect
            key={i}
            x={(i % space.width) * CELL}
            y={Math.floor(i / space.width) * CELL}
            width={CELL}
            height={CELL}
            className="cell"
          />
        ))
      ) : (
        <>
          {space.edges.map(([a, b], i) => {
            const from = space.nodes.find((n) => n.id === a);
            const to = space.nodes.find((n) => n.id === b);
            if (!from || !to) return null;
            return (
              <line
                key={i}
                x1={(from.x + 1.2) * 200}
                y1={(from.y + 1.2) * 200}
                x2={(to.x + 1.2) * 200}
                y2={(to.y + 1.2) * 200}
                className="edge"
              />
            );
          })}
          {space.nodes.map((node) => (
            <g key={node.id}>
              <circle cx={(node.x + 1.2) * 200} cy={(node.y + 1.2) * 200} r={20} className="node" />
              <text x={(node.x + 1.2) * 200} y={(node.y + 1.2) * 200 + 34} className="node-label">
                {node.id}
              </text>
            </g>
          ))}
        </>
      )}
      {frame.units.map((unit) => {
        const spot = place(space, unit);
        if (!spot) return null;
        const key = spot.join(",");
        const offset = seen.get(key) ?? 0;
        seen.set(key, offset + 1);
        const [cx, cy] = [spot[0] + offset * 8, spot[1] - offset * 8];
        const destroyed = unit.status === "destroyed";
        const share = unit.hp !== null && unit.max_hp ? Math.max(unit.hp, 0) / unit.max_hp : 0;
        return (
          <g key={unit.entity_id} className="unit" data-unit={unit.entity_id} data-status={unit.status}>
            <title>{`${unit.name}: ${destroyed ? "destroyed" : `${unit.hp} hp`}`}</title>
            <circle
              cx={cx}
              cy={cy}
              r={14}
              fill={destroyed ? "var(--surface)" : factionColor(unit.faction)}
              stroke={factionColor(unit.faction)}
              strokeWidth={2}
              strokeDasharray={destroyed ? "3 3" : undefined}
            />
            <text x={cx} y={cy + 4} className="unit-label">
              {unit.name
                .split(" ")
                .map((word) => word[0])
                .join("")}
            </text>
            {!destroyed && (
              <>
                <rect x={cx - 16} y={cy + 17} width={32} height={4} className="hp-back" />
                <rect x={cx - 16} y={cy + 17} width={32 * share} height={4} className="hp-bar" />
              </>
            )}
          </g>
        );
      })}
    </svg>
  );
}
