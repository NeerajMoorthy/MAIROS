import { CheckCircle2, FileText, Layers, Library, Loader2, Network, XCircle } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { ProjectStats } from "@/lib/api";

interface StatProps {
  icon: typeof FileText;
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
}

function Stat({ icon: Icon, label, value, sub }: StatProps) {
  return (
    <Card className="rounded-xl border border-frozen/15 bg-black-iris/60 backdrop-blur-md transition-all hover:border-frozen/40 hover:shadow-[0_0_15px_rgba(160,189,219,0.1)]">
      <CardContent className="flex items-start gap-3 p-3.5">
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-frozen/25 bg-frozen/10 text-frozen">
          <Icon className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <p className="text-lg font-semibold leading-none text-foreground">{value}</p>
          <p className="mt-1 truncate text-xs text-frozen/75">{label}</p>
          {sub && <div className="mt-1.5">{sub}</div>}
        </div>
      </CardContent>
    </Card>
  );
}

/** Project Overview: the counts a returning user needs at a glance. */
export function ProjectOverview({ stats }: { stats: ProjectStats | null }) {
  if (!stats) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-[74px] rounded-xl border border-frozen/10 bg-black-iris/40" />
        ))}
      </div>
    );
  }

  const counts = stats.task_counts;
  // A run waiting for its turn is as much in progress as one under way.
  const active = counts.running + counts.queued;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      <Stat icon={FileText} label="Documents uploaded" value={stats.documents} />
      <Stat icon={Layers} label="Indexed chunks" value={stats.chunks} />
      <Stat icon={Library} label="Papers discovered" value={stats.papers} />
      <Stat icon={Network} label="Graph nodes / edges" value={`${stats.graph.nodes} / ${stats.graph.edges}`} />
      <Stat
        icon={Loader2}
        label="Tasks running"
        value={active}
        sub={
          active > 0 ? (
            <span className="inline-flex items-center gap-1 text-[10px] font-medium text-frozen">
              <Loader2 className="h-2.5 w-2.5 animate-spin" /> in progress
              {counts.queued > 0 && ` · ${counts.queued} waiting to start`}
            </span>
          ) : undefined
        }
      />
      <Stat
        icon={CheckCircle2}
        label={`Tasks completed${counts.failed ? " · failed" : ""}`}
        value={
          <span>
            {counts.completed}
            {counts.failed > 0 && (
              <span className="ml-1.5 inline-flex items-center gap-0.5 text-sm font-medium text-destructive">
                <XCircle className="h-3.5 w-3.5" />
                {counts.failed}
              </span>
            )}
          </span>
        }
      />
    </div>
  );
}

export default ProjectOverview;
