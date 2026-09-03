import type { FlyaiFlightItem } from "../types/travel";

export type FlightTicketView = {
  key: string;
  airline: string;
  flightNo: string;
  depTime: string;
  arrTime: string;
  depPlace: string;
  arrPlace: string;
  price: string;
  meta: string[];
};

const PRICE_KEYS = [
  "adultPrice",
  "adultTaxPrice",
  "price",
  "lowestPrice",
  "minPrice",
  "lowestAdultPrice",
  "ticketPrice",
  "totalPrice",
  "showPrice",
  "salePrice",
  "childPrice",
] as const;

function pick(obj: Record<string, unknown> | undefined, ...keys: string[]): string {
  if (!obj) return "";
  for (const k of keys) {
    const v = obj[k];
    if (v !== undefined && v !== null && String(v).trim()) return String(v).trim();
  }
  return "";
}

function timeShort(value: string): string {
  const v = value.trim();
  if (v.includes(" ")) return v.split(" ").pop()!.slice(0, 5);
  if (v.includes(":")) return v.slice(0, 5);
  return v;
}

function station(obj: Record<string, unknown>, prefix: string): string {
  const name = pick(
    obj,
    `${prefix}StationShortName`,
    `${prefix}Airport`,
    `${prefix}AirportName`,
    `${prefix}City`,
    `${prefix}CityName`,
    `${prefix}StationName`,
    `${prefix}Place`,
  );
  const term = pick(obj, `${prefix}Term`);
  return name && term ? `${name}${term}` : name;
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function legs(item: Record<string, unknown>): Record<string, unknown>[] {
  const journeys = item.journeys;
  if (Array.isArray(journeys) && journeys.length) {
    const first = asRecord(journeys[0]);
    const segs = first?.segments;
    if (Array.isArray(segs)) {
      const out: Record<string, unknown>[] = [];
      for (const s of segs) {
        const sr = asRecord(s);
        if (sr) out.push(sr);
      }
      if (out.length) return out;
    }
  }
  return [item];
}

function plainPrice(value: unknown): string {
  if (value === undefined || value === null || value === "") return "";
  const text = String(value).replace(/¥/g, "").replace(/,/g, "").trim();
  if (!text || text === "—" || text === "-") return "";
  const n = Number(text);
  if (!Number.isNaN(n) && n <= 0) return "";
  return text;
}

export function extractPrice(obj: Record<string, unknown>): string {
  for (const key of PRICE_KEYS) {
    const v = plainPrice(obj[key]);
    if (v) return v;
  }
  const nested = obj.price;
  if (nested && typeof nested === "object" && !Array.isArray(nested)) {
    const rec = nested as Record<string, unknown>;
    for (const key of PRICE_KEYS) {
      const v = plainPrice(rec[key]);
      if (v) return v;
    }
  } else {
    const v = plainPrice(nested);
    if (v) return v;
  }
  const journeys = obj.journeys;
  if (Array.isArray(journeys)) {
    const parts: number[] = [];
    for (const j of journeys) {
      const jr = asRecord(j);
      if (!jr) continue;
      const p = extractPrice(jr);
      if (p) {
        const n = Number(p);
        if (!Number.isNaN(n)) parts.push(n);
      }
    }
    if (parts.length === 1) return String(parts[0]);
    if (parts.length > 1) return String(parts.reduce((a, b) => a + b, 0));
  }
  return "";
}

export function flattenFlight(item: FlyaiFlightItem | Record<string, unknown>): {
  airline: string;
  flightNo: string;
  depTime: string;
  arrTime: string;
  depPlace: string;
  arrPlace: string;
  price: string;
  cabin: string;
} {
  const rec = item as Record<string, unknown>;
  const segs = legs(rec);
  const first = segs[0] || rec;
  const last = segs[segs.length - 1] || rec;
  const price = extractPrice(rec) || extractPrice(first);
  return {
    airline: pick(first, "marketingTransportName", "airlineName", "airline") || pick(rec, "airlineName", "airline"),
    flightNo:
      pick(first, "marketingTransportNo", "flightNo", "flightNoCn", "trainNo") ||
      pick(rec, "flightNo", "flightNoCn", "trainNo"),
    depTime: timeShort(pick(first, "depDateTime", "depTime")),
    arrTime: timeShort(pick(last, "arrDateTime", "arrTime")),
    depPlace: station(first, "dep"),
    arrPlace: station(last, "arr"),
    price,
    cabin: pick(first, "seatClassName", "cabin") || pick(rec, "cabin"),
  };
}

export function formatPlanPrice(value: number | string | null | undefined): string {
  if (value === undefined || value === null || value === "") return "—";
  const n = Number(String(value).replace(/¥/g, ""));
  if (!Number.isNaN(n)) return `¥${n}`;
  const s = String(value);
  return s.startsWith("¥") ? s : `¥${s}`;
}

export function segmentSummary(seg: Record<string, unknown> | string): string {
  if (typeof seg === "string") return seg.trim();
  const summary = seg.summary ?? seg.detail ?? seg.description;
  if (typeof summary === "string" && summary.trim()) {
    const raw = summary.trim();
    if (raw.startsWith("{")) {
      try {
        const parsed = JSON.parse(raw) as Record<string, unknown>;
        return segmentSummary(parsed);
      } catch {
        return raw.length > 120 ? `${raw.slice(0, 120)}…` : raw;
      }
    }
    return raw.length > 160 ? `${raw.slice(0, 160)}…` : raw;
  }
  const flat = flattenFlight(seg);
  const bits = [
    flat.flightNo,
    flat.depPlace || flat.arrPlace ? `${flat.depPlace || "?"}→${flat.arrPlace || "?"}` : "",
    flat.depTime || flat.arrTime ? `${flat.depTime}${flat.depTime && flat.arrTime ? "–" : ""}${flat.arrTime}` : "",
    flat.price ? `¥${flat.price}` : "",
  ].filter(Boolean);
  if (bits.length) return bits.join(" ");
  return seg.type ? String(seg.type) : "行程";
}

export function flightSignature(item: FlyaiFlightItem): string {
  const f = flattenFlight(item);
  return `${f.flightNo}|${f.depTime}|${f.depPlace}|${f.arrPlace}`;
}

export function dedupeFlights(items: FlyaiFlightItem[]): FlyaiFlightItem[] {
  const seen = new Set<string>();
  const out: FlyaiFlightItem[] = [];
  for (const item of items) {
    const sig = flightSignature(item);
    if (seen.has(sig)) continue;
    seen.add(sig);
    out.push(item);
  }
  return out;
}

export function toFlightTicket(item: FlyaiFlightItem, index: number): FlightTicketView {
  const f = flattenFlight(item);
  const meta: string[] = [];
  if (f.cabin) meta.push(f.cabin);
  const rec = item as Record<string, unknown>;
  const stop = pick(rec, "stopInfo", "transferInfo");
  if (stop) meta.push(stop);
  else if (item.isDirect === true || pick(rec, "journeyType") === "1" || pick(rec, "journeyType") === "直达") {
    meta.push("直飞");
  }
  const duration = pick(rec, "duration", "flyTime", "flightTime", "totalDuration");
  if (duration) meta.push(String(duration));
  return {
    key: `${f.flightNo || "flight"}-${f.depTime}-${index}`,
    airline: f.airline || "—",
    flightNo: f.flightNo || "航班",
    depTime: f.depTime || "—",
    arrTime: f.arrTime || "—",
    depPlace: f.depPlace || "—",
    arrPlace: f.arrPlace || "—",
    price: f.price ? `¥${f.price}` : "—",
    meta,
  };
}
