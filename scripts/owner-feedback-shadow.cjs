const { spawnSync } = require("node:child_process");
const { join } = require("node:path");

const effort = process.env.SHADOW_REVIEW_EFFORT;
const context = process.env.SHADOW_REVIEW_CONTEXT;
if (!effort || !context) {
  throw new Error("The verified review profile settings are required.");
}
const deadline = new Date(Date.now() + 30 * 60 * 1000).toISOString();
console.log(`Invocation budget: 30 minutes; finish by ${deadline}.`);
const result = spawnSync(
  "timeout",
  [
    "--verbose",
    "--kill-after=30s",
    "30m",
    process.execPath,
    join(__dirname, "copilot_harness.cjs"),
    process.argv[2],
    "--reasoning-effort",
    effort,
    "--context",
    context,
    ...process.argv.slice(3),
  ],
  {
    stdio: "inherit",
    env: {
      ...process.env,
      AI_BUDGET_MINUTES: "30",
      AI_DEADLINE_UTC: deadline,
    },
  },
);
if (result.error) throw result.error;
if (result.signal) console.error(`Shadow harness terminated by ${result.signal}`);
process.exit(result.status ?? 1);
