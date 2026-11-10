"use client";

import { useState } from "react";
import Status from "@/components/Status";
import { type Chain, runApi, useApi } from "@/lib/api";

function Chains({ chains }: { chains: Chain[] }) {
  const [onlyLosses, setOnlyLosses] = useState(false);
  const shown = onlyLosses ? chains.filter((c) => c.event_types.includes("ENTITY_DESTROYED")) : chains;
  return (
    <>
      <div className="controls">
        <label>
          <input type="checkbox" checked={onlyLosses} onChange={(e) => setOnlyLosses(e.target.checked)} /> Only
          actions that destroyed a unit
        </label>
        <span className="muted">
          {shown.length} of {chains.length} actions
        </span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th className="num">Tick</th>
              <th>Who</th>
              <th>Against</th>
              <th>What it caused</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((chain) => (
              <tr key={chain.action_id}>
                <td className="num">{chain.tick}</td>
                <td>{chain.actor}</td>
                <td>{chain.target ?? "—"}</td>
                <td>
                  {chain.event_types.map((type) => (
                    <span className="badge" key={type}>
                      {type.replaceAll("_", " ").toLowerCase()}
                    </span>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export default function CausalPage() {
  const loaded = useApi<{ chains: Chain[] }>(runApi("causal"));
  return (
    <>
      <h1>Causal chain</h1>
      <p className="lede">Every action and the events it caused, in the order they happened.</p>
      <Status loaded={loaded}>{(data) => <Chains chains={data.chains} />}</Status>
    </>
  );
}
