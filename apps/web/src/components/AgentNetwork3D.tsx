"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  motion,
  useAnimationFrame,
  useMotionValue,
  useReducedMotion,
  useTransform,
} from "framer-motion";
import { BrainCircuit } from "lucide-react";

import { AGENTS, FLOWS, agentColor, flowSteps, type AgentInfo } from "@/lib/agents";
import { cn } from "@/lib/utils";

/** Degrees the ring plane leans back from the viewer. */
const TILT = 58;
/** Degrees per second the ring turns. */
const SPIN = 6;

/** The ring's radius, sized to the stage so it fits at phone width. */
function useRadius() {
  const stage = useRef<HTMLDivElement>(null);
  const [radius, setRadius] = useState(220);
  useEffect(() => {
    const node = stage.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      const width = entry.contentRect.width;
      // Narrow stages leave room for the labels at the ring's ends.
      if (width > 0) setRadius(Math.max(105, Math.min(260, width * (width < 640 ? 0.3 : 0.4))));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return { stage, radius };
}

/**
 * The orchestrator and its agents as a slowly turning 3D ring. Picking a flow
 * lights the agents it assigns, numbered in the order they run, and sends work
 * along their links. Built from DOM elements and CSS 3D transforms, so labels
 * stay crisp, need no WebGL, and the list below repeats everything for screen
 * readers.
 */
export function AgentNetwork3D() {
  const reduceMotion = useReducedMotion();
  const { stage, radius } = useRadius();
  const [flowId, setFlowId] = useState<string | null>("search");
  const angle = useMotionValue(0);
  const counter = useTransform(angle, (a) => -a);

  useAnimationFrame((_, delta) => {
    if (!reduceMotion) angle.set((angle.get() + (SPIN * delta) / 1000) % 360);
  });

  const flow = FLOWS.find((f) => f.id === flowId) ?? null;
  const steps = useMemo(() => (flow ? flowSteps(flow) : []), [flow]);
  const byId = useMemo(() => new Map(AGENTS.map((a) => [a.id, a])), []);

  return (
    <section aria-labelledby="agent-map-title" className="rounded-2xl border border-frozen/15 bg-black-iris/40 p-4 backdrop-blur-sm sm:p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="agent-map-title" className="text-lg font-semibold">
            How the work is divided
          </h2>
          <p className="mt-1 max-w-xl text-sm text-muted-foreground">
            The Orchestrator&apos;s Router reads each request and picks a flow; each flow hands the
            work to a fixed team of agents, in order. Pick a flow to see its team.
          </p>
        </div>
      </div>

      <div role="group" aria-label="Flow" className="mt-4 flex flex-wrap gap-2">
        <FlowChip active={flowId === null} onClick={() => setFlowId(null)}>
          All agents
        </FlowChip>
        {FLOWS.map((f) => (
          <FlowChip key={f.id} active={flowId === f.id} onClick={() => setFlowId(f.id)}>
            {f.label}
          </FlowChip>
        ))}
      </div>

      <div
        ref={stage}
        aria-hidden="true"
        data-testid="agent-map-stage"
        className="relative mt-2 h-[320px] select-none overflow-hidden sm:h-[460px]"
        style={{ perspective: 1100 }}
      >
        <div
          className="absolute left-1/2 top-[58%] h-0 w-0"
          style={{ transformStyle: "preserve-3d", transform: `rotateX(${TILT}deg)` }}
        >
          <motion.div className="absolute h-0 w-0" style={{ rotateZ: angle, transformStyle: "preserve-3d" }}>
            {/* Orbit rings on the floor of the scene. */}
            {[1, 0.62].map((scale) => (
              <div
                key={scale}
                className="absolute rounded-full border border-frozen/15"
                style={{
                  width: radius * 2 * scale,
                  height: radius * 2 * scale,
                  left: -radius * scale,
                  top: -radius * scale,
                }}
              />
            ))}

            {AGENTS.map((agent, i) => {
              const theta = (360 / AGENTS.length) * i;
              const step = steps.indexOf(agent.id);
              const lit = flow === null || step >= 0;
              return (
                <div key={agent.id} style={{ transformStyle: "preserve-3d" }}>
                  <Spoke agent={agent} theta={theta} radius={radius} lit={lit} order={step} busy={!!flow && !reduceMotion} />
                  <div
                    className="absolute h-0 w-0"
                    style={{
                      transform: `rotate(${theta}deg) translateX(${radius}px) rotate(${-theta}deg)`,
                      transformStyle: "preserve-3d",
                    }}
                  >
                    {/* Undo the ring's turn and tilt so the card faces the viewer. */}
                    <motion.div style={{ rotateZ: counter, transformStyle: "preserve-3d" }}>
                      <div style={{ transform: `rotateX(${-TILT}deg)`, transformStyle: "preserve-3d" }}>
                        <AgentNode agent={agent} lit={lit} order={step} />
                      </div>
                    </motion.div>
                  </div>
                </div>
              );
            })}

            <motion.div style={{ rotateZ: counter, transformStyle: "preserve-3d" }} className="absolute h-0 w-0">
              <div style={{ transform: `rotateX(${-TILT}deg)`, transformStyle: "preserve-3d" }}>
                <OrchestratorCore pulsing={!reduceMotion} />
              </div>
            </motion.div>
          </motion.div>
        </div>
      </div>

      <FlowLegend steps={steps} byId={byId} flowLabel={flow?.label ?? null} />
    </section>
  );
}

function FlowChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "focus-ring rounded-full border px-3 py-1 text-xs font-medium transition-colors",
        active
          ? "border-frozen/60 bg-frozen/20 text-frozen shadow-[0_0_14px_rgba(160,189,219,0.25)]"
          : "border-frozen/15 text-muted-foreground hover:border-frozen/40 hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

/** A link from the core to an agent, with a packet of work travelling out. */
function Spoke({
  agent,
  theta,
  radius,
  lit,
  order,
  busy,
}: {
  agent: AgentInfo;
  theta: number;
  radius: number;
  lit: boolean;
  order: number;
  busy: boolean;
}) {
  const working = busy && order >= 0;
  return (
    <div
      className="absolute left-0 top-0 h-[2px] origin-left transition-opacity duration-500"
      style={{
        width: radius,
        transform: `rotate(${theta}deg)`,
        opacity: lit ? 1 : 0.12,
        background: `linear-gradient(90deg, rgba(160,189,219,0.35), ${agentColor(agent, 0.8)})`,
      }}
    >
      {working && (
        <motion.span
          className="absolute -top-[3px] h-2 w-2 rounded-full"
          style={{ background: agentColor(agent), boxShadow: `0 0 10px ${agentColor(agent)}` }}
          initial={{ left: "0%", opacity: 0 }}
          animate={{ left: ["0%", "100%"], opacity: [0, 1, 0] }}
          transition={{ duration: 1.6, delay: order * 0.35, repeat: Infinity, repeatDelay: 1.2, ease: "easeInOut" }}
        />
      )}
    </div>
  );
}

function AgentNode({ agent, lit, order }: { agent: AgentInfo; lit: boolean; order: number }) {
  return (
    <div
      className="absolute flex w-max -translate-x-1/2 -translate-y-full items-center gap-1 whitespace-nowrap rounded-lg border px-1.5 py-0.5 text-[10px] sm:gap-1.5 sm:px-2 sm:py-1 font-medium backdrop-blur-md transition-all duration-500 sm:text-xs"
      style={{
        borderColor: agentColor(agent, lit ? 0.75 : 0.2),
        background: lit ? agentColor(agent, 0.16) : "rgba(8,8,19,0.6)",
        color: lit ? agentColor(agent) : "rgba(160,189,219,0.35)",
        boxShadow: lit && order >= 0 ? `0 0 18px ${agentColor(agent, 0.35)}` : "none",
      }}
    >
      {order >= 0 && (
        <span
          className="grid h-4 w-4 place-items-center rounded-full text-[10px] font-bold text-black-iris"
          style={{ background: agentColor(agent) }}
        >
          {order}
        </span>
      )}
      {agent.label}
    </div>
  );
}

function OrchestratorCore({ pulsing }: { pulsing: boolean }) {
  return (
    <div className="absolute w-max -translate-x-1/2 -translate-y-full">
      <motion.div
        className="relative grid h-16 w-16 place-items-center rounded-2xl border border-frozen/50 bg-black-iris/80 text-frozen shadow-[0_0_40px_rgba(160,189,219,0.25)] sm:h-28 sm:w-28"
        animate={pulsing ? { boxShadow: ["0 0 24px rgba(160,189,219,0.2)", "0 0 48px rgba(160,189,219,0.45)", "0 0 24px rgba(160,189,219,0.2)"] } : undefined}
        transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
      >
        <div className="flex flex-col items-center gap-1">
          <BrainCircuit className="h-6 w-6 sm:h-8 sm:w-8" />
          <span className="text-[10px] font-semibold tracking-wide sm:text-xs">Orchestrator</span>
        </div>
      </motion.div>
    </div>
  );
}

/** The same information as the scene, as text: the steps, or every agent. */
function FlowLegend({
  steps,
  byId,
  flowLabel,
}: {
  steps: string[];
  byId: Map<string, AgentInfo>;
  flowLabel: string | null;
}) {
  const agents = flowLabel ? steps.map((id) => byId.get(id)).filter((a): a is AgentInfo => !!a) : AGENTS;
  return (
    <div className="mt-2">
      <h3 className="text-sm font-medium text-foreground">
        {flowLabel ? `${flowLabel}: ${agents.length} agents, in order` : `All ${agents.length} agents`}
      </h3>
      <ol className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {agents.map((agent, i) => (
          <li
            key={agent.id}
            className="flex items-start gap-2 rounded-lg border border-frozen/10 bg-black-iris/50 p-2.5 text-sm"
          >
            <span
              aria-hidden="true"
              className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full text-[10px] font-bold text-black-iris"
              style={{ background: agentColor(agent) }}
            >
              {flowLabel ? i : ""}
            </span>
            <span>
              <span className="font-medium" style={{ color: agentColor(agent) }}>
                {agent.label}
              </span>
              <span className="block text-xs text-muted-foreground">{agent.role}</span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
