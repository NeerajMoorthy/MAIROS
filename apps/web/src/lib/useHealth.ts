"use client";

import { useEffect, useState } from "react";

import { api, type HealthInfo } from "@/lib/api";

/**
 * Shared backend-health poll. Several panels need to know whether the LLM is
 * live (to show honest system-state notices) without each opening its own
 * interval — this is the one place that polls `/health`.
 */
export function useHealth(intervalMs = 20000) {
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let active = true;
    const check = () =>
      api
        .health()
        .then((info) => {
          if (!active) return;
          setHealth(info);
          setOffline(false);
        })
        .catch(() => active && setOffline(true));

    check();
    const timer = setInterval(check, intervalMs);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [intervalMs]);

  return { health, offline };
}
