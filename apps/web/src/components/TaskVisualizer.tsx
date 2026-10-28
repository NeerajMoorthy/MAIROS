"use client";

import { useCallback, useState } from "react";

import { AgentActivity } from "@/components/AgentActivity";
import { AgentNetwork3D } from "@/components/AgentNetwork3D";
import type { Task } from "@/lib/api";
import { FLOWS } from "@/lib/agents";

/**
 * The agent map with the runs under it. Picking a run lights the agents its
 * flow assigned, so the map shows that run; picking a flow chip still browses
 * any flow.
 */
export function TaskVisualizer() {
  const [flowId, setFlowId] = useState<string | null>("search");
  const [run, setRun] = useState<Task | null>(null);

  const showRun = useCallback((task: Task | null) => {
    setRun(task);
    const flow = task ? (task.flow ?? task.result?.routing?.flow ?? null) : null;
    if (flow && FLOWS.some((f) => f.id === flow)) setFlowId(flow);
  }, []);

  const runFlow = run ? (run.flow ?? run.result?.routing?.flow ?? null) : null;
  const caption =
    run && runFlow === flowId ? (
      <>
        Lit agents: run <span className="font-mono">#{run.id.slice(0, 6)}</span> “{run.request}”
      </>
    ) : null;

  return (
    <AgentNetwork3D flowId={flowId} onFlowChange={setFlowId} caption={caption}>
      <div className="mt-6 border-t border-frozen/10 pt-5">
        <AgentActivity onRunChange={showRun} />
      </div>
    </AgentNetwork3D>
  );
}
