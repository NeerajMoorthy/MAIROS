"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { useReducedMotion } from "framer-motion";

import { cn } from "@/lib/utils";

// three.js is ~600 kB; keep it out of the page bundle and off the server.
const ResearchConstellation = dynamic(() => import("./ResearchConstellation"), {
  ssr: false,
  loading: () => null,
});

/** True when the browser can create a WebGL context. */
export function supportsWebGL(): boolean {
  if (typeof document === "undefined") return false;
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

/**
 * The decorative 3D scene for page heroes. Renders nothing (the ambient
 * background shows through) when WebGL is missing or the user prefers reduced
 * motion, and stops the render loop while scrolled out of view.
 */
export function Hero3D({ className }: { className?: string }) {
  const reduceMotion = useReducedMotion();
  const container = useRef<HTMLDivElement>(null);
  const [enabled, setEnabled] = useState(false);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    setEnabled(supportsWebGL());
  }, []);

  useEffect(() => {
    const node = container.current;
    if (!node || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting));
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const show = enabled && !reduceMotion;

  return (
    <div
      ref={container}
      aria-hidden="true"
      data-testid="hero-3d"
      data-state={show ? "on" : "off"}
      className={cn("pointer-events-auto", className)}
    >
      {show && <ResearchConstellation active={visible} />}
    </div>
  );
}
