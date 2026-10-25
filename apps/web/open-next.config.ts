// OpenNext adapter configuration for Cloudflare Workers.
// https://opennext.js.org/cloudflare
//
// Defaults are deliberate: MAIROS pages are client-rendered dashboards with no
// ISR or fetch cache to persist, so no R2/KV incremental cache is configured.
import { defineCloudflareConfig } from "@opennextjs/cloudflare";

export default defineCloudflareConfig();
