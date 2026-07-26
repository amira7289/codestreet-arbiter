/**
 * Design tokens.
 *
 * The categorical ramp was validated with the dataviz palette checker before use —
 * lightness band, chroma floor, CVD adjacent-pair separation (worst 8.8 deutan),
 * normal-vision floor (worst 19.3), and contrast against the light surface all pass.
 * Do not add or reorder hues without re-running that check: series colour follows the
 * entity, never its rank, so a reorder silently repaints every chart in the app.
 */

// Brand. Blue-forward and restrained, in the register of a card issuer's own tooling.
export const BRAND = {
  blue: "#006FCF",
  blueDeep: "#00175A",
  blueInk: "#001235",
  blueTint: "#E8F2FC",
  blueTintStrong: "#CFE5F9",
};

export const INK = {
  primary: "#16181A",
  secondary: "#53565A",
  muted: "#8A8D91",
  inverse: "#FFFFFF",
};

export const SURFACE = {
  page: "#F4F6F8",
  card: "#FFFFFF",
  sunken: "#F7F9FB",
  border: "#DCE1E6",
  borderStrong: "#C3CAD1",
};

// Reserved for state. Never reused as a series colour.
export const STATUS = {
  good: "#00875A",
  goodTint: "#E3F3EC",
  warning: "#B35A00",
  warningTint: "#FBEFE3",
  critical: "#B02A37",
  criticalTint: "#FBEAEC",
  neutral: "#53565A",
  neutralTint: "#EEF1F4",
};

// Fixed order. Index 0 and 1 are the two disputing parties and are load-bearing
// across the whole app, so they are named rather than positional.
export const CATEGORICAL = ["#006FCF", "#A8500A", "#1A7F5A", "#7B4EA8", "#B02A37"];

export const PARTY = {
  card_member: CATEGORICAL[0],
  merchant: CATEGORICAL[1],
};

export const PARTY_LABEL = {
  card_member: "Card Member",
  merchant: "Merchant",
};

export const CLAIM_COLOR = {
  item_not_received: CATEGORICAL[0],
  refund_not_processed: CATEGORICAL[1],
  not_as_described: CATEGORICAL[2],
  duplicate_charge: CATEGORICAL[3],
};

export const STATUS_STYLE = {
  filed: { fg: STATUS.neutral, bg: STATUS.neutralTint, label: "Filed" },
  evidence_gathering: { fg: STATUS.warning, bg: STATUS.warningTint, label: "Gathering Evidence" },
  scored: { fg: BRAND.blue, bg: BRAND.blueTint, label: "Scored" },
  resolved: { fg: STATUS.good, bg: STATUS.goodTint, label: "Resolved" },
};

export const titleCase = (s) =>
  String(s || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

export const money = (n) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n ?? 0);

export const pct = (n, digits = 0) =>
  n == null ? "—" : `${(n * 100).toFixed(digits)}%`;
