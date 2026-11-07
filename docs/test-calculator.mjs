// Replays data/measurements.json through the web calculator math.
import fs from "node:fs";
import assert from "node:assert/strict";
import { GiB, countedMemory, estimateBytes, inUseBytes, limitBytes, willLoad } from "./calculator.mjs";

const data = JSON.parse(fs.readFileSync(new URL("../data/measurements.json", import.meta.url), "utf8"));
const sizes = Object.fromEntries(data.reports.flatMap((r) => r.rows.map((x) => [x.model, x.size_bytes])));
let n = 0;
for (const report of data.reports) {
  const m = report.machine;
  const limit = limitBytes(report.guardrail_mode, countedMemory(m.ram_bytes, m.vram_bytes, m.platform));
  const inUse = inUseBytes(report.loaded_models.map((k) => sizes[k]));
  for (const row of report.rows) {
    const est = estimateBytes(row.size_bytes, row.format, row.type);
    if (est !== null && row.lms_estimate_bytes !== null) assert.ok(Math.abs(est - row.lms_estimate_bytes) <= 0.006 * GiB, row.model);
    const v = willLoad(est, inUse, limit);
    if (v !== null && row.lms_will_load !== null) assert.equal(v, row.lms_will_load, `${report.scenario}: ${row.model}`);
    n++;
  }
}
assert.equal(limitBytes("balanced", 32 * GiB) / GiB, 25.6);
for (const p of data.probes ?? []) {
  const m = p.machine;
  const limit = limitBytes(p.guardrail_mode, countedMemory(m.ram_bytes, m.vram_bytes, m.platform));
  const predicted = limit - inUseBytes(Object.values(p.loaded_model_sizes));
  assert.ok(Math.abs(p.max_accepted_estimate_bytes - predicted) <= 0.05 * GiB, p.scenario);
  n++;
}
console.log(`ok - ${n} measurements reproduced`);
