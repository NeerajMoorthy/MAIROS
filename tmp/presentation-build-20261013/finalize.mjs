import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const SKILL_DIR = "C:/Users/moort/.codex/plugins/cache/openai-primary-runtime/presentations/26.1011.11113/skills/presentations";
const workspaceDir = "C:/Users/moort/SEM THREE/AI_ML/Project/mairos";
const candidatePath = path.join(workspaceDir, "tmp/presentation-build-20261013/MAIROS_Project_Walkthrough_draft.pptx");
const finalPath = path.join(workspaceDir, "output/presentations/MAIROS_Project_Walkthrough_2026-10-13.pptx");
const stagingDir = path.join(workspaceDir, "tmp/presentation-build-20261013/finalizer");
await fs.mkdir(stagingDir, { recursive: true });
const { finalizePresentation } = await import(pathToFileURL(
  path.join(SKILL_DIR, "container_tools/artifact_tool_utils.mjs"),
).href);

const result = await finalizePresentation({
  workspaceDir,
  candidatePath,
  finalPath,
  pythonExecutable: "C:/Users/moort/SEM THREE/AI_ML/Project/mairos/.venv/Scripts/python.exe",
  integrityValidatorPath: path.join(SKILL_DIR, "container_tools/inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(SKILL_DIR, "container_tools/inspect_presentation_layout_geometry.py"),
  layoutArgs: [
    "--expected-slide-size-emu", "12192000,6858000",
    "--validate-bullet-geometry",
    "--validate-heading-fit",
  ],
  explicitTotalSlideCount: 16,
  requiredNativeTableOwnerSlides: [],
  requiredNativeChartOwnerSlides: [],
  fontPolicy: { basis: "design", families: ["Arial"] },
  verifyArtifactToolImport: true,
  receiptPath: path.join(stagingDir, "MAIROS_Project_Walkthrough_2026-10-13.validation.json"),
});
console.log(JSON.stringify(result, null, 2));
