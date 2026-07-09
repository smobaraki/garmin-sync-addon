/**
 * Norwegian human-readable labels for Garmin enum / localization keys.
 *
 * Garmin does NOT publish an official enum dictionary — values like
 * `POSITIVE_LONG_AND_DEEP` are localization keys resolved inside the Garmin
 * Connect app. This module ships curated Norwegian labels faithful to Garmin's
 * meaning, plus a deterministic fallback humanizer so unknown/new keys never
 * render raw and you never need an LLM at render time.
 *
 * Usage:
 *   import { labelFor, labelForColumn } from "./enum_labels";
 *
 *   labelFor("sleep_score_feedback", sleep.sleep_score_feedback).label;
 *   // → "Lang og dyp søvn"
 *
 *   labelForColumn("body_battery_event.short_feedback", ev.short_feedback);
 *   // → { label: "Avslappende blund", sentiment: "positive" }
 *
 *   labelForColumn("training_load.training_status", 8);
 *   // → { label: "Anstrengt", description: "...", sentiment: "negative" }
 */

import raw from "./enum_labels.json";

export type Sentiment = "positive" | "negative" | "neutral";

export interface EnumLabel {
  label: string;
  description?: string;
  sentiment: Sentiment;
}

type Domain = Record<string, EnumLabel>;

const DATA = raw as unknown as {
  _meta: {
    description: string;
    sentiment_values: Sentiment[];
    column_domains: Record<string, string>;
  };
} & Record<string, Domain>;

const COLUMN_DOMAINS: Record<string, string> = DATA._meta.column_domains;

/**
 * Look up a curated label for a `(domain, key)` pair. Falls back to a
 * deterministic humanization of the key when no curated entry exists, so the
 * return value is always safe to render.
 *
 * @param domain e.g. "sleep_score_feedback", "training_status"
 * @param key    the raw DB value (string or number)
 */
export function labelFor(domain: string, key: string | number | null | undefined): EnumLabel {
  if (key === null || key === undefined || key === "") {
    return { label: "—", sentiment: "neutral" };
  }
  const k = String(key);
  const table = DATA[domain] as Domain | undefined;
  const hit = table?.[k];
  if (hit) return hit;
  return humanize(k);
}

/**
 * Convenience wrapper that resolves the domain from a fully-qualified column
 * name (e.g. "sleep.sleep_score_feedback"). Unknown columns fall back to
 * humanizing the value directly.
 */
export function labelForColumn(column: string, key: string | number | null | undefined): EnumLabel {
  const domain = COLUMN_DOMAINS[column];
  if (domain) return labelFor(domain, key);
  return labelFor("__unknown__", key);
}

/**
 * Deterministic fallback: turn a raw enum key into a readable label + sentiment
 * without any lookup table. Handles UPPER_SNAKE_CASE and camelCase, and derives
 * sentiment from a leading POSITIVE_/NEGATIVE_ token.
 *
 *   "POSITIVE_SUPER_CALM" → { label: "Super calm", sentiment: "positive" }
 *   "highlyActive"        → { label: "Highly active", sentiment: "neutral" }
 */
export function humanize(key: string): EnumLabel {
  let sentiment: Sentiment = "neutral";
  let rest = key;

  const upper = key.toUpperCase();
  if (upper.startsWith("POSITIVE_") || upper === "POSITIVE") {
    sentiment = "positive";
    rest = key.slice("POSITIVE".length).replace(/^_/, "");
  } else if (upper.startsWith("NEGATIVE_") || upper === "NEGATIVE") {
    sentiment = "negative";
    rest = key.slice("NEGATIVE".length).replace(/^_/, "");
  } else if (upper === "NONE" || upper === "INVALID") {
    return { label: upper === "NONE" ? "Ingen" : "Mangler data", sentiment: "neutral" };
  }

  const words = rest
    // split camelCase → camel Case
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    // underscores / dashes → spaces
    .replace(/[_-]+/g, " ")
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean);

  if (words.length === 0) {
    return { label: sentiment === "neutral" ? "—" : cap(sentiment), sentiment };
  }
  words[0] = cap(words[0]);
  return { label: words.join(" "), sentiment };
}

function cap(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** The raw curated data, exposed for tooling / tests. */
export const enumLabels = DATA;
export const columnDomains = COLUMN_DOMAINS;
