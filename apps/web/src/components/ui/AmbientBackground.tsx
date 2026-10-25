"use client";

import { motion } from "framer-motion";

/**
 * Ambient background component inspired by Haikei.app and motion-primitives.com.
 *
 * Implements:
 * - Black Iris (#080813 / rgb(8, 8, 19)) deep obsidian foundation.
 * - Frozen (#A0BDDB / rgb(160, 189, 219)) ethereal accent waves, glowing blobs, and grid.
 * - Haikei layered organic wave paths with delicate gradient fills.
 * - Scientific precision coordinate lattice with radial vignette falloff.
 * - Smooth, subtle Framer Motion ambient breathing (GPU accelerated, zero layout impact).
 */
export function AmbientBackground() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 -z-10 overflow-hidden select-none bg-[#080813]"
    >
      {/* 1. Subtle SVG coordinate lattice / dot-grid with radial vignette */}
      <svg
        className="absolute inset-0 h-full w-full opacity-60"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <pattern
            id="haikei-grid"
            width="40"
            height="40"
            patternUnits="userSpaceOnUse"
          >
            <circle cx="20" cy="20" r="1" fill="#A0BDDB" fillOpacity="0.12" />
            <path
              d="M 40 0 L 0 0 0 40"
              fill="none"
              stroke="#A0BDDB"
              strokeWidth="0.5"
              strokeOpacity="0.035"
            />
          </pattern>
          <radialGradient id="grid-vignette" cx="50%" cy="40%" r="65%">
            <stop offset="0%" stopColor="#fff" stopOpacity="1" />
            <stop offset="60%" stopColor="#fff" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#fff" stopOpacity="0" />
          </radialGradient>
          <mask id="grid-mask">
            <rect width="100%" height="100%" fill="url(#grid-vignette)" />
          </mask>
        </defs>
        <rect
          width="100%"
          height="100%"
          fill="url(#haikei-grid)"
          mask="url(#grid-mask)"
        />
      </svg>

      {/* 2. Ambient glowing organic blobs (Haikei Blob Scene + Motion Primitives) */}
      <motion.div
        className="absolute -top-[15%] -right-[10%] h-[550px] w-[550px] rounded-full blur-[110px]"
        style={{
          background:
            "radial-gradient(circle, rgba(160, 189, 219, 0.18) 0%, rgba(8, 8, 19, 0) 70%)",
        }}
        animate={{
          scale: [1, 1.08, 0.96, 1],
          opacity: [0.7, 0.95, 0.65, 0.7],
          x: [0, 20, -15, 0],
          y: [0, -15, 20, 0],
        }}
        transition={{
          duration: 18,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      />

      <motion.div
        className="absolute top-[40%] -left-[12%] h-[600px] w-[600px] rounded-full blur-[130px]"
        style={{
          background:
            "radial-gradient(circle, rgba(160, 189, 219, 0.12) 0%, rgba(18, 20, 42, 0.25) 45%, rgba(8, 8, 19, 0) 75%)",
        }}
        animate={{
          scale: [1, 0.92, 1.06, 1],
          opacity: [0.5, 0.8, 0.55, 0.5],
          x: [0, -25, 15, 0],
          y: [0, 25, -20, 0],
        }}
        transition={{
          duration: 22,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      />

      {/* 3. Layered organic SVG wave paths (Haikei Layered Waves) */}
      <svg
        className="absolute bottom-0 left-0 w-full opacity-40 mix-blend-screen"
        viewBox="0 0 1440 320"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id="wave-grad-1" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#A0BDDB" stopOpacity="0.14" />
            <stop offset="50%" stopColor="#080813" stopOpacity="0.04" />
            <stop offset="100%" stopColor="#A0BDDB" stopOpacity="0.08" />
          </linearGradient>
          <linearGradient id="wave-grad-2" x1="100%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#A0BDDB" stopOpacity="0.09" />
            <stop offset="100%" stopColor="#080813" stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* Deep organic wave layer 1 */}
        <path
          d="M0,192L48,197.3C96,203,192,213,288,208C384,203,480,181,576,176C672,171,768,181,864,197.3C960,213,1056,235,1152,224C1248,213,1344,171,1392,149.3L1440,128L1440,320L1392,320C1344,320,1248,320,1152,320C1056,320,960,320,864,320C768,320,672,320,576,320C480,320,384,320,288,320C192,320,96,320,48,320L0,320Z"
          fill="url(#wave-grad-1)"
        />
        {/* Soft flowing wave layer 2 */}
        <path
          d="M0,256L60,240C120,224,240,192,360,197.3C480,203,600,245,720,245.3C840,245,960,203,1080,186.7C1200,171,1320,181,1380,186.7L1440,192L1440,320L1380,320C1320,320,1200,320,1080,320C960,320,840,320,720,320C600,320,480,320,360,320C240,320,120,320,60,320L0,320Z"
          fill="url(#wave-grad-2)"
        />
      </svg>
    </div>
  );
}
