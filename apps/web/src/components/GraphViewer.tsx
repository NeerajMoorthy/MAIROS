"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { AlertCircle, Loader2, Network, RefreshCw } from "lucide-react";

import { SystemNotice } from "@/components/SystemNotice";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { api, type GraphData, type GraphNode } from "@/lib/api";
import { describeError } from "@/lib/errorMessage";

// react-force-graph touches `window` on import, so it must be client-only.
// next/dynamic does not forward refs, so wrap it and pass the ref through
// `innerRef` — without this, zoomToFit and the d3 force handles are unreachable.
const ForceGraph2D = dynamic(
  async () => {
    const mod = await import("react-force-graph-2d");
    const Component = mod.default;
    function ForceGraphWithRef({ innerRef, ...props }: any) {
      return <Component ref={innerRef} {...props} />;
    }
    return ForceGraphWithRef;
  },
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    ),
  },
);

/** Shorten a label so long paper titles do not smear across the canvas. */
/** A d3 force that pulls every node gently towards the origin. */
function towardsCentre(strength: number) {
  let nodes: { x?: number; y?: number; vx?: number; vy?: number }[] = [];
  const force = (alpha: number) => {
    for (const node of nodes) {
      node.vx = (node.vx ?? 0) - (node.x ?? 0) * strength * alpha;
      node.vy = (node.vy ?? 0) - (node.y ?? 0) * strength * alpha;
    }
  };
  force.initialize = (all: typeof nodes) => {
    nodes = all;
  };
  return force;
}

function truncate(value: string, max: number): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

const GROUP_COLOURS: Record<string, string> = {
  Paper: "#6366f1",
  Person: "#f59e0b",
  Method: "#10b981",
  Concept: "#38bdf8",
  Dataset: "#f43f5e",
  Metric: "#a855f7",
  Task: "#14b8a6",
  Patent: "#eab308",
  Unknown: "#94a3b8",
};

// The backend's entity type is "Person" (services/knowledge_graph); the UI
// calls it "Author" per the reviewer's terminology. Display-only mapping —
// the API contract is untouched.
const GROUP_LABELS: Record<string, string> = { Person: "Author" };
function displayLabel(group: string): string {
  return GROUP_LABELS[group] ?? group;
}

// Always-shown legend, per the Stage 1 spec, independent of what's currently
// in the graph — Patent is reserved for a future patent-analysis flow and
// will simply read 0 until an agent produces one.
const LEGEND_TYPES = ["Paper", "Person", "Concept", "Method", "Dataset", "Patent", "Metric", "Task"];

/** Tab (d): force-directed view of the knowledge graph built so far. */
export function GraphViewer({ projectId }: { projectId: string }) {
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [size, setSize] = useState({ width: 800, height: 560 });
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<any>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .getGraph(projectId)
      .then((graph) => {
        setData(graph);
        setSelected(null);
      })
      .catch((err) => setError(describeError(err, "Could not load the knowledge graph.")))
      .finally(() => setLoading(false));
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  // Keep the canvas sized to its container — the old fixed 800x600 clipped it.
  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;

    const update = () =>
      setSize({
        width: element.clientWidth,
        height: Math.max(360, element.clientHeight),
      });

    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [data]);

  // The layout forces are set the moment the graph component attaches. They
  // used to be set in an effect on `data`, which ran before the lazily loaded
  // component existed, so it returned early and the default forces were used:
  // a tight blob, or disconnected clusters flung to the edges.
  const attachGraph = useCallback((graph: any) => {
    graphRef.current = graph;
    if (!graph) return;
    // Spread nodes enough for their labels, within a limited range.
    graph.d3Force("charge")?.strength(-260).distanceMax(240);
    graph.d3Force("link")?.distance(70);
    // Papers that share no concept form separate clusters; a weak pull to the
    // centre keeps them side by side instead of flung apart.
    graph.d3Force("gravity", towardsCentre(0.05));
    graph.d3ReheatSimulation?.();
  }, []);

  useEffect(() => {
    if (!data?.nodes.length) return;
    const timer = setTimeout(() => graphRef.current?.zoomToFit?.(500, 60), 1600);
    return () => clearTimeout(timer);
  }, [data]);

  // A fixed legend (not just the groups present) so the key is a reference,
  // not a summary that disappears when a type has zero nodes yet.
  const legend = useMemo(() => {
    const counts = new Map<string, number>();
    for (const node of data?.nodes ?? []) {
      counts.set(node.group, (counts.get(node.group) ?? 0) + 1);
    }
    const known = LEGEND_TYPES.map((group) => [group, counts.get(group) ?? 0] as const);
    const extra = [...counts.entries()].filter(([group]) => !LEGEND_TYPES.includes(group));
    return [...known, ...extra];
  }, [data]);

  const isEmpty = !loading && !error && (data?.nodes.length ?? 0) === 0;

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b px-6 py-3">
        <Badge variant="secondary">
          <Network className="h-3 w-3" /> {data?.stats.nodes ?? 0} nodes ·{" "}
          {data?.stats.edges ?? 0} edges
        </Badge>
        {legend.map(([group, count]) => (
          <Badge
            key={group}
            variant="outline"
            className={`gap-1.5 ${count === 0 ? "opacity-45" : ""}`}
            title={count === 0 ? `${displayLabel(group)} — none yet` : undefined}
          >
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: GROUP_COLOURS[group] ?? GROUP_COLOURS.Unknown }}
            />
            {displayLabel(group)} ({count})
          </Badge>
        ))}
        <Button variant="ghost" size="sm" className="ml-auto" onClick={load}>
          <RefreshCw /> Refresh
        </Button>
      </div>

      <div ref={containerRef} className="relative min-h-0 flex-1">
        {error ? (
          <div role="alert" className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
            <AlertCircle className="h-8 w-8 text-destructive" />
            <div>
              <h3 className="font-medium">Could not load the knowledge graph</h3>
              <p className="mt-1 text-sm text-muted-foreground">{error}</p>
            </div>
            <Button variant="outline" onClick={load}>Retry</Button>
          </div>
        ) : isEmpty ? (
          <div className="flex h-full flex-col items-center justify-center px-6 text-center">
            <Network className="mb-4 h-10 w-10 text-muted-foreground/40" />
            <h3 className="font-medium">The knowledge graph is empty</h3>
            <p className="mt-1.5 max-w-md text-sm text-muted-foreground">
              Upload a PDF or run a topic search. The Knowledge Graph agent adds
              papers, authors, and extracted concepts after each run.
            </p>
          </div>
        ) : loading ? (
          <div className="flex h-full items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <ForceGraph2D
            innerRef={attachGraph}
            graphData={data as GraphData}
            width={size.width}
            height={size.height}
            backgroundColor="rgba(0,0,0,0)"
            nodeRelSize={4}
            nodeVal={(node: any) => node.val ?? 2}
            nodeLabel={(node: any) =>
              `${node.name} (${displayLabel(node.group)})${node.description ? ` — ${node.description}` : ""}`
            }
            nodeColor={(node: any) => GROUP_COLOURS[node.group] ?? GROUP_COLOURS.Unknown}
            // Draw the node plus its label; an unlabelled graph is unreadable
            // in a demo, and hover-only tooltips do not survive a screenshot.
            nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, scale: number) => {
              const radius = Math.sqrt(node.val ?? 2) * 4;
              ctx.beginPath();
              ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI);
              ctx.fillStyle = GROUP_COLOURS[node.group] ?? GROUP_COLOURS.Unknown;
              ctx.fill();

              if (scale < 0.55) return; // too zoomed out for text to be legible

              const label = truncate(node.name, 26);
              const fontSize = Math.max(9, 11 / Math.sqrt(scale));
              ctx.font = `${fontSize}px ui-sans-serif, system-ui, sans-serif`;
              ctx.textAlign = "center";
              ctx.textBaseline = "top";
              ctx.lineWidth = 3;
              ctx.strokeStyle = "rgba(9,9,11,0.85)";
              ctx.strokeText(label, node.x, node.y + radius + 2);
              ctx.fillStyle = "rgba(228,232,241,0.92)";
              ctx.fillText(label, node.x, node.y + radius + 2);
            }}
            nodePointerAreaPaint={(node: any, colour: string, ctx: CanvasRenderingContext2D) => {
              ctx.fillStyle = colour;
              ctx.beginPath();
              ctx.arc(node.x, node.y, Math.sqrt(node.val ?? 2) * 4 + 3, 0, 2 * Math.PI);
              ctx.fill();
            }}
            linkLabel={(link: any) => link.label}
            linkColor={() => "rgba(148,163,184,0.35)"}
            linkDirectionalArrowLength={3}
            linkDirectionalArrowRelPos={1}
            linkWidth={0.8}
            cooldownTicks={200}
            d3VelocityDecay={0.32}
            onEngineStop={() => graphRef.current?.zoomToFit?.(500, 60)}
            onNodeClick={(node: any) => setSelected(node as GraphNode)}
          />
        )}

        {selected && (
          <Card className="absolute bottom-4 left-4 right-4 max-w-sm shadow-lg sm:right-auto">
            <CardContent className="p-4">
              <div className="mb-1.5 flex items-start justify-between gap-3">
                <p className="font-medium">{selected.name}</p>
                <Button
                  variant="ghost"
                  size="sm"
                  className="-mr-2 -mt-1 h-6 px-2 text-xs"
                  onClick={() => setSelected(null)}
                >
                  Close
                </Button>
              </div>
              <Badge variant="outline">{displayLabel(selected.group)}</Badge>
              {selected.description && (
                <p className="mt-2 text-sm text-muted-foreground">
                  {selected.description}
                </p>
              )}
              <p className="mt-2 text-xs text-muted-foreground">
                Mentioned {selected.mentions}×
              </p>
              {selected.group === "Patent" && (
                <SystemNotice variant="patent" className="mt-3" />
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

export default GraphViewer;
