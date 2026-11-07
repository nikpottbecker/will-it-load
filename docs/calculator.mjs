// Shared math for the web calculator. Mirrors src/will_it_load/model.py — keep both in sync
// (CI runs docs/test-calculator.mjs against data/measurements.json).
export const GiB = 1024 ** 3;
export const MiB = 1024 ** 2;
export const CUTOFF = 16 * GiB;
export const FACTOR = 1.4;
export const PROFILES = {
  strict: [0.65, 0.85],
  balanced: [0.75, 0.85],
  relaxed: [0.85, 0.9],
};
// Extra memory a loaded model holds beyond its file size (measured, see data/measurements.json probes).
export const OVERHEAD = 0.58 * GiB;

export function inUseBytes(loadedSizes) {
  return loadedSizes.reduce((a, s) => a + s + OVERHEAD, 0);
}

export function countedMemory(ram, vram, platform) {
  return platform === "darwin" ? ram : ram + vram;
}

export function limitBytes(mode, total, custom = 0) {
  if (mode === "off") return Infinity;
  if (mode === "custom") return custom;
  const [lo, hi] = PROFILES[mode];
  return Math.min(total, CUTOFF) * lo + Math.max(0, total - CUTOFF) * hi;
}

export function estimateBytes(size, format = "safetensors", kind = "llm") {
  if (format === "gguf" && (kind === "llm" || kind === "vlm")) return null;
  return size * FACTOR;
}

export function willLoad(estimate, inUse, limit) {
  if (estimate === null) return null;
  return inUse + estimate <= limit;
}

export function fmt(n) {
  if (n === null || n === undefined) return "?";
  if (n === Infinity) return "unlimited";
  const s = n < 0 ? "-" : "";
  n = Math.abs(n);
  return n >= GiB ? `${s}${(n / GiB).toFixed(2)} GiB` : `${s}${(n / MiB).toFixed(2)} MiB`;
}
