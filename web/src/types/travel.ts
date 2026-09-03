// P4 TRAVEL-PLAN-1 差旅类型（后端契约见 docs/TECH.md「P4 Master 入口」）

import { extractPrice } from "../utils/flightDisplay";

// flyai search-flight 响应 itemList 单项原结构（字段透传，不归一化）
export type FlyaiFlightItem = Record<string, unknown> & {
  flightNo?: string;
  airlineName?: string;
  depAirport?: string;
  arrAirport?: string;
  depTime?: string;
  arrTime?: string;
  depDate?: string;
  price?: number | string;
  lowestPrice?: number | string;
  minPrice?: number | string;
  adultPrice?: number | string;
};

export type HotelPlaceholder = {
  kind: "placeholder";
  message: string;
};

export type TravelError = {
  kind: "error";
  message: string;
};

export type PlanOption = {
  id: string;
  label: string;
  segments?: Array<Record<string, unknown>>;
  total_price?: number | string | null;
  notes?: string;
};

export type PlanComparison = {
  dimension: string;
  rows: Array<{ option_id: string; value: unknown }>;
};

export type PlanRecommendation = {
  option_id: string;
  reason: string;
};

// plan_itinerary 输出（方案页契约，不绑 flyai 字段）
export type TravelPlan = {
  options: PlanOption[];
  comparison: PlanComparison[];
  recommendation: PlanRecommendation | null;
  total_price_summary: string;
};

export type PlanHtmlEvent = {
  html?: string;
  url?: string | null;
  key?: string | null;
  note?: string;
};

export type TravelData = {
  flights?: FlyaiFlightItem[];
  hotels?: HotelPlaceholder | TravelError | Record<string, unknown>;
  plan?: TravelPlan;
};

export function flightPrice(item: FlyaiFlightItem): string {
  const raw = extractPrice(item as Record<string, unknown>);
  return raw ? `¥${raw}` : "—";
}

export function flightLabel(item: FlyaiFlightItem): string {
  return (
    item.flightNo ||
    String((item as Record<string, unknown>).flightNoCn || "") ||
    "航班"
  );
}


// TRAVEL-BOOK-1 HITL 待确认动作
export type PendingAction = {
  tool: "book_flight" | "book_hotel" | "cancel";
  args: Record<string, unknown>;
  summary: string;
  confirmed?: boolean | null;
};

// TRAVEL-BOOK-1 预订列表 / 单笔结果
export type BookingItem = {
  id: string;
  kind: string;
  vendor?: string;
  external_id?: string | null;
  status: string;
  pay_url?: string | null;
  payload?: Record<string, unknown>;
  created_at?: string | null;
};
