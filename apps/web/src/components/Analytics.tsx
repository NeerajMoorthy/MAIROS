import Script from "next/script";

import { GA_MEASUREMENT_ID } from "@/lib/config";

/**
 * Google Analytics 4 — page views only, and only when a measurement id is
 * configured at build time.
 *
 * Research content never leaves through here: no custom events are sent, and
 * GA4 sees page paths (which carry project ids, never project names, queries
 * or documents). IP anonymisation is on and Google Signals / ad
 * personalisation are off. App Router navigations are counted by GA4's
 * enhanced measurement of history changes, so no route listener is needed.
 */
export function Analytics() {
  if (!/^G-[A-Z0-9]+$/.test(GA_MEASUREMENT_ID)) return null;

  return (
    <>
      <Script
        src={`https://www.googletagmanager.com/gtag/js?id=${GA_MEASUREMENT_ID}`}
        strategy="afterInteractive"
      />
      <Script id="ga4-init" strategy="afterInteractive">
        {`window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('js', new Date());
gtag('config', '${GA_MEASUREMENT_ID}', {
  anonymize_ip: true,
  allow_google_signals: false,
  allow_ad_personalization_signals: false
});`}
      </Script>
    </>
  );
}

export default Analytics;
