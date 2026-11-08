"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Status from "@/components/Status";
import WorldMap, { factionColor } from "@/components/WorldMap";
import { type Frame, type MapData, useApi } from "@/lib/api";

type Message =
  | { type: "ready"; first: number; last: number }
  | { type: "frame"; frame: Frame }
  | { type: "end"; tick: number }
  | { type: "paused"; tick: number | null }
  | { type: "error"; message: string };

/** Frames arrive over the replay WebSocket: seek one, or play them in order. */
function useReplay(first: Frame) {
  const socket = useRef<WebSocket | null>(null);
  const [frame, setFrame] = useState<Frame>(first);
  const [range, setRange] = useState<[number, number] | null>(null);
  const [playing, setPlaying] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${scheme}://${window.location.host}/ws/replay`);
    socket.current = ws;
    ws.onmessage = (event) => {
      const message = JSON.parse(event.data) as Message;
      if (message.type === "ready") setRange([message.first, message.last]);
      else if (message.type === "frame") setFrame(message.frame);
      else if (message.type === "end" || message.type === "paused") setPlaying(false);
      else if (message.type === "error") setProblem(message.message);
    };
    ws.onerror = () => setProblem("The replay connection failed.");
    return () => ws.close();
  }, []);

  const send = useCallback((message: object) => {
    socket.current?.send(JSON.stringify(message));
  }, []);

  return {
    frame,
    range,
    playing,
    problem,
    seek: (tick: number) => send({ type: "seek", tick }),
    play: (from: number) => {
      setPlaying(true);
      send({ type: "play", from, interval_ms: 700 });
    },
    pause: () => send({ type: "pause" }),
  };
}

function Player({ data }: { data: MapData }) {
  const replay = useReplay(data.frames[0]);
  const { frame, range } = replay;
  const ready = range !== null;
  const [first, last] = range ?? [0, 0];
  const atEnd = frame.tick >= last;

  return (
    <div className="replay">
      <div>
        <WorldMap space={data.space} frame={frame} />
        <div className="controls">
          <button onClick={() => replay.seek(frame.tick - 1)} disabled={!ready || frame.tick <= first}>
            Previous
          </button>
          {replay.playing ? (
            <button onClick={replay.pause}>Pause</button>
          ) : (
            <button onClick={() => replay.play(atEnd ? first : frame.tick + 1)} disabled={!ready}>
              Play
            </button>
          )}
          <button onClick={() => replay.seek(frame.tick + 1)} disabled={!ready || atEnd}>
            Next
          </button>
          <input
            type="range"
            aria-label="Tick"
            min={first}
            max={last}
            value={frame.tick}
            disabled={!ready}
            onChange={(event) => replay.seek(Number(event.target.value))}
          />
        </div>
        {replay.problem && <p className="notice error">{replay.problem}</p>}
      </div>
      <div>
        <h2 style={{ marginTop: 0 }} aria-live="polite">
          {frame.tick === 0 ? "Start" : `Tick ${frame.tick}`}
        </h2>
        {frame.lines.length === 0 ? (
          <p className="muted">Units in their starting positions.</p>
        ) : (
          <ul className="plain">
            {frame.lines.map((line, index) => (
              <li key={index}>{line}</li>
            ))}
          </ul>
        )}
        <h2>Units</h2>
        <table>
          <thead>
            <tr>
              <th>Unit</th>
              <th>Side</th>
              <th className="num">HP</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {frame.units.map((unit) => (
              <tr key={unit.entity_id}>
                <td>{unit.name}</td>
                <td style={{ color: factionColor(unit.faction) }}>{unit.faction}</td>
                <td className="num">
                  {unit.hp} / {unit.max_hp}
                </td>
                <td>{unit.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function ReplayPage() {
  const loaded = useApi<MapData>("/api/map");
  return (
    <>
      <h1>Replay</h1>
      <p className="lede">
        The world at the end of each tick. Step through it or play it; hover a unit for its hp.
      </p>
      <Status loaded={loaded}>{(data) => <Player data={data} />}</Status>
    </>
  );
}
