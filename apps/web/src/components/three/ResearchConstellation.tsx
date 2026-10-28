"use client";

import { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";

/**
 * A 3D "research constellation": papers and concepts as nodes on a sphere,
 * linked to their nearest neighbours, orbiting an orchestrator core. It mirrors
 * how MAIROS works (one orchestrator, many agents, a knowledge graph) and is
 * purely decorative.
 *
 * Loaded only on the client through `Hero3D`, which skips it when WebGL is
 * unavailable or the user prefers reduced motion.
 */

const FROZEN = "#A0BDDB";
const NODE_COUNT = 72;
const RADIUS = 2.1;
const LINKS_PER_NODE = 3;

/** Evenly spread points on a sphere, jittered so it reads as organic. */
function constellationPoints(count: number, radius: number): THREE.Vector3[] {
  const points: THREE.Vector3[] = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  // A fixed-seed generator keeps the layout identical between renders.
  let seed = 7;
  const random = () => {
    seed = (seed * 16807) % 2147483647;
    return (seed - 1) / 2147483646;
  };
  for (let i = 0; i < count; i++) {
    const y = 1 - (i / (count - 1)) * 2;
    const ring = Math.sqrt(1 - y * y);
    const theta = golden * i;
    const r = radius * (0.82 + random() * 0.3);
    points.push(new THREE.Vector3(Math.cos(theta) * ring * r, y * r, Math.sin(theta) * ring * r));
  }
  return points;
}

/** Line-segment positions joining each node to its nearest neighbours. */
function linkPositions(points: THREE.Vector3[], perNode: number): Float32Array {
  const seen = new Set<string>();
  const segments: number[] = [];
  points.forEach((point, i) => {
    const nearest = points
      .map((other, j) => ({ j, d: point.distanceToSquared(other) }))
      .filter(({ j }) => j !== i)
      .sort((a, b) => a.d - b.d)
      .slice(0, perNode);
    for (const { j } of nearest) {
      const key = i < j ? `${i}-${j}` : `${j}-${i}`;
      if (seen.has(key)) continue;
      seen.add(key);
      segments.push(point.x, point.y, point.z, points[j].x, points[j].y, points[j].z);
    }
  });
  return new Float32Array(segments);
}

function Constellation() {
  const group = useRef<THREE.Group>(null);
  const core = useRef<THREE.Mesh>(null);
  const halo = useRef<THREE.Mesh>(null);
  const nodes = useRef<THREE.InstancedMesh>(null);

  const points = useMemo(() => constellationPoints(NODE_COUNT, RADIUS), []);
  const links = useMemo(() => linkPositions(points, LINKS_PER_NODE), [points]);
  const scratch = useMemo(() => new THREE.Object3D(), []);

  useFrame(({ clock, pointer }, delta) => {
    const t = clock.getElapsedTime();
    if (group.current) {
      group.current.rotation.y += delta * 0.08;
      // Ease toward the pointer for a gentle parallax.
      group.current.rotation.x = THREE.MathUtils.lerp(group.current.rotation.x, pointer.y * 0.35, 0.04);
      group.current.rotation.z = THREE.MathUtils.lerp(group.current.rotation.z, -pointer.x * 0.15, 0.04);
    }
    if (core.current) {
      core.current.rotation.x = t * 0.3;
      core.current.rotation.y = t * 0.45;
    }
    if (halo.current) {
      const pulse = 1 + Math.sin(t * 1.6) * 0.06;
      halo.current.scale.setScalar(pulse);
    }
    if (nodes.current) {
      points.forEach((point, i) => {
        const breathe = 0.85 + Math.sin(t * 1.3 + i * 0.7) * 0.25;
        scratch.position.copy(point);
        scratch.scale.setScalar(breathe);
        scratch.updateMatrix();
        nodes.current!.setMatrixAt(i, scratch.matrix);
      });
      nodes.current.instanceMatrix.needsUpdate = true;
    }
  });

  return (
    <group ref={group}>
      <lineSegments>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[links, 3]} />
        </bufferGeometry>
        <lineBasicMaterial color={FROZEN} transparent opacity={0.18} />
      </lineSegments>

      <instancedMesh ref={nodes} args={[undefined, undefined, NODE_COUNT]}>
        <sphereGeometry args={[0.045, 12, 12]} />
        <meshBasicMaterial color={FROZEN} toneMapped={false} />
      </instancedMesh>

      <mesh ref={core}>
        <icosahedronGeometry args={[0.62, 1]} />
        <meshStandardMaterial
          color={FROZEN}
          emissive={FROZEN}
          emissiveIntensity={0.35}
          wireframe
          transparent
          opacity={0.75}
        />
      </mesh>
      <mesh ref={halo}>
        <sphereGeometry args={[0.42, 32, 32]} />
        <meshBasicMaterial color={FROZEN} transparent opacity={0.12} />
      </mesh>

      {[0, 1, 2].map((i) => (
        <mesh key={i} rotation={[Math.PI / 2 + i * 0.6, i * 0.9, 0]}>
          <torusGeometry args={[1.05 + i * 0.22, 0.004, 8, 128]} />
          <meshBasicMaterial color={FROZEN} transparent opacity={0.28 - i * 0.06} />
        </mesh>
      ))}
    </group>
  );
}

export default function ResearchConstellation({ active = true }: { active?: boolean }) {
  return (
    <Canvas
      camera={{ position: [0, 0, 6], fov: 45 }}
      dpr={[1, 1.75]}
      gl={{ antialias: true, alpha: true, powerPreference: "low-power" }}
      frameloop={active ? "always" : "never"}
      aria-hidden="true"
    >
      <ambientLight intensity={0.6} />
      <pointLight position={[4, 4, 4]} intensity={18} color={FROZEN} />
      <Constellation />
    </Canvas>
  );
}
