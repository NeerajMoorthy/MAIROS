"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  AlertCircle,
  ArrowRight,
  FileText,
  FolderOpen,
  Library,
  Loader2,
  Plus,
  Sparkles,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { TiltCard } from "@/components/ui/tilt-card";
import { Hero3D } from "@/components/three/Hero3D";
import { forgetActiveProjectId, setActiveProjectId } from "@/lib/activeProject";
import { api, type Project } from "@/lib/api";
import { describeError } from "@/lib/errorMessage";

export default function ProjectsPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [projectToDelete, setProjectToDelete] = useState<Project | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    try {
      const list = await api.listProjects();
      setProjects(list);
      setError(null);
    } catch (err) {
      setError(describeError(err, "Failed to load projects"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleOpenWorkspace = (projectId: string) => {
    setActiveProjectId(projectId);
    router.push(`/projects/${projectId}`);
  };

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;

    setCreating(true);
    try {
      const project = await api.createProject(name.trim(), description.trim());
      setActiveProjectId(project.id);
      setDialogOpen(false);
      setName("");
      setDescription("");
      router.push(`/projects/${project.id}`);
    } catch (err) {
      setError(describeError(err, "Failed to create project"));
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete() {
    if (!projectToDelete) return;

    setDeleting(true);
    try {
      await api.deleteProject(projectToDelete.id);
      setProjects((current) => current.filter((project) => project.id !== projectToDelete.id));
      forgetActiveProjectId(projectToDelete.id);
      setProjectToDelete(null);
      setError(null);
    } catch (err) {
      setError(describeError(err, "Failed to delete project"));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="relative mx-auto w-full max-w-6xl p-6 md:p-10">
      <header className="relative mb-10 grid items-center gap-6 overflow-hidden rounded-2xl border border-frozen/15 bg-black-iris/40 px-6 py-8 backdrop-blur-sm md:grid-cols-[1fr_minmax(260px,380px)] md:px-10">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_80%_50%,rgba(160,189,219,0.14),transparent_60%)]"
        />
        <motion.div
          className="relative"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
        >
          <span className="inline-flex items-center gap-1 rounded-full border border-frozen/30 bg-frozen/10 px-2.5 py-0.5 text-xs font-medium text-frozen">
            <Sparkles className="h-3 w-3" /> MAIROS Core
          </span>
          <h1 className="mt-3 bg-gradient-to-br from-white via-frozen to-frozen/60 bg-clip-text text-4xl font-semibold tracking-tight text-transparent md:text-5xl">
            Research Projects
          </h1>
          <p className="mt-3 max-w-md text-sm text-frozen/80 md:text-base">
            Each project has its own document library, knowledge graph, and agent history.
          </p>
          <Button
            onClick={() => setDialogOpen(true)}
            className="mt-6 border border-frozen/40 bg-frozen text-black-iris font-semibold hover:bg-frozen/90 shadow-[0_0_20px_rgba(160,189,219,0.25)] transition-all hover:-translate-y-0.5 hover:shadow-[0_10px_30px_rgba(160,189,219,0.35)]"
          >
            <Plus /> New Project
          </Button>
        </motion.div>
        <Hero3D className="relative -my-4 hidden h-[260px] md:block lg:h-[300px]" />
      </header>

      {error && (
        <Card className="mb-6 border-destructive/50 bg-black-iris/70 backdrop-blur-md">
          <CardContent className="flex items-center gap-3 p-4 text-sm">
            <AlertCircle className="h-4 w-4 shrink-0 text-destructive" />
            <span>{error}</span>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-44 w-full rounded-xl border border-frozen/10 bg-black-iris/40" />
          ))}
        </div>
      ) : projects.length === 0 ? (
        <Card className="border-dashed border-frozen/25 bg-black-iris/50 backdrop-blur-md">
          <CardContent className="flex flex-col items-center justify-center py-20 text-center">
            <div className="mb-4 rounded-full border border-frozen/25 bg-frozen/10 p-4 text-frozen">
              <FolderOpen className="h-7 w-7 text-frozen" />
            </div>
            <h3 className="text-lg font-medium text-foreground">No projects yet</h3>
            <p className="mt-1.5 max-w-sm text-sm text-frozen/80">
              Create a project, then upload a PDF or search a topic to start the
              multi-agent pipeline.
            </p>
            <Button
              className="mt-6 border-frozen/30 hover:bg-frozen/15 hover:text-frozen"
              variant="outline"
              onClick={() => setDialogOpen(true)}
            >
              <Plus /> Create your first project
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project, idx) => (
            <motion.div
              key={project.id}
              initial={{ opacity: 0, y: 24, rotateX: -12 }}
              animate={{ opacity: 1, y: 0, rotateX: 0 }}
              transition={{ duration: 0.45, delay: Math.min(idx * 0.06, 0.36), ease: "easeOut" }}
              style={{ transformPerspective: 900 }}
              className="min-w-0"
            >
              <TiltCard className="h-full">
                <Card className="group flex h-full flex-col rounded-xl border border-frozen/20 bg-black-iris/70 backdrop-blur-md transition-all duration-300 hover:border-frozen/50 hover:shadow-[0_8px_30px_rgba(160,189,219,0.14)]">
                  <CardHeader className="pb-4">
                    <CardTitle className="truncate text-lg text-foreground group-hover:text-frozen transition-colors">
                      {project.name}
                    </CardTitle>
                    <CardDescription className="line-clamp-2 h-10 text-muted-foreground">
                      {project.description || "No description provided."}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-wrap gap-2 pb-4">
                    <Badge
                      variant="secondary"
                      className="border border-frozen/20 bg-frozen/10 text-frozen"
                    >
                      <FileText className="h-3 w-3 mr-1" /> {project.num_documents} docs
                    </Badge>
                    <Badge
                      variant="secondary"
                      className="border border-frozen/20 bg-frozen/10 text-frozen"
                    >
                      <Library className="h-3 w-3 mr-1" /> {project.num_papers} papers
                    </Badge>
                  </CardContent>
                  <CardFooter className="mt-auto gap-2 pt-2">
                    <Button
                      variant="outline"
                      className="flex-1 border-frozen/30 bg-transparent text-foreground hover:border-frozen hover:bg-frozen/15 hover:text-frozen transition-all"
                      onClick={() => handleOpenWorkspace(project.id)}
                    >
                      Open workspace <ArrowRight className="ml-1 h-4 w-4 transition-transform group-hover:translate-x-1" />
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      aria-label={`Delete ${project.name}`}
                      className="shrink-0 border-destructive/50 bg-transparent text-destructive hover:bg-destructive hover:text-destructive-foreground"
                      onClick={() => setProjectToDelete(project)}
                    >
                      <Trash2 />
                    </Button>
                  </CardFooter>
                </Card>
              </TiltCard>
            </motion.div>
          ))}
        </div>
      )}

      <Dialog open={dialogOpen} onOpenChange={(open) => !creating && setDialogOpen(open)}>
        <DialogContent className="border border-frozen/25 bg-black-iris text-foreground shadow-2xl backdrop-blur-2xl sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-xl font-semibold tracking-tight text-foreground">
              New research project
            </DialogTitle>
            <DialogDescription className="text-sm text-frozen/80">
              A workspace with its own vector index and knowledge graph.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleCreate} className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="project-name" className="text-sm font-medium text-foreground">
                Project name
              </label>
              <Input
                id="project-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. Retrieval-Augmented Generation survey"
                disabled={creating}
                autoFocus
                required
                className="border-frozen/25 bg-black-iris/60 focus-visible:border-frozen focus-visible:ring-frozen"
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="project-description" className="text-sm font-medium text-foreground">
                Description <span className="text-frozen/60">(optional)</span>
              </label>
              <Input
                id="project-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="What is this research about?"
                disabled={creating}
                className="border-frozen/25 bg-black-iris/60 focus-visible:border-frozen focus-visible:ring-frozen"
              />
            </div>
            <DialogFooter className="gap-2 pt-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setDialogOpen(false)}
                disabled={creating}
                className="hover:bg-frozen/10 text-muted-foreground hover:text-foreground"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={creating || !name.trim()}
                className="border border-frozen/40 bg-frozen text-black-iris font-semibold hover:bg-frozen/90 shadow-[0_0_15px_rgba(160,189,219,0.25)]"
              >
                {creating && <Loader2 className="animate-spin mr-1 h-4 w-4" />}
                Create project
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog
        open={projectToDelete !== null}
        onOpenChange={(open) => !open && !deleting && setProjectToDelete(null)}
      >
        <DialogContent className="border border-destructive/40 bg-black-iris text-foreground sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete project?</DialogTitle>
            <DialogDescription>
              This permanently removes “{projectToDelete?.name}”, its uploaded files, indexed chunks,
              knowledge graph, papers, and task history.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 pt-2">
            <Button
              type="button"
              variant="ghost"
              disabled={deleting}
              onClick={() => setProjectToDelete(null)}
            >
              Cancel
            </Button>
            <Button type="button" variant="destructive" disabled={deleting} onClick={handleDelete}>
              {deleting && <Loader2 className="animate-spin" />}
              Delete project
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
