/**
 * Browser smoke test of the UI served by SKYVAULT itself (Phase 17; Phase 21).
 *
 *   skyvault serve &
 *   skyvault explore military_urban_001/v0.2 --repeat 2
 *   skyvault batch military_doctrine --repeat 5
 *   skyvault run military_urban_001/v0.2
 *   SKYVAULT_URL=http://127.0.0.1:8000 node e2e/smoke.mjs
 *
 * Opens every page in Chromium and checks that it shows what the service
 * says about the newest run — read first from the service's own API — as
 * sentences and tables a person can read, not JSON: the timeline tick by
 * tick, the replay stepping, the failure map, the comparison, both briefing
 * downloads, and the run picker. CHROMIUM_PATH points at a browser binary
 * when Playwright's own is absent.
 */

import assert from "node:assert/strict";
import { chromium } from "playwright";

const BASE = process.env.SKYVAULT_URL ?? "http://127.0.0.1:8000";

async function api(path) {
  const response = await fetch(`${BASE}${path}`);
  assert.ok(response.ok, `${path}: ${response.status}`);
  return response.json();
}

const runs = await api("/api/runs");
assert.ok(runs.length > 0, "the service has no run: submit one first");
const newest = runs[0];
const overview = await api("/api/runs/latest/overview");
const timeline = await api("/api/runs/latest/timeline");
const map = await api("/api/runs/latest/map");
const causal = await api("/api/runs/latest/causal");
const failure = await api("/api/runs/latest/failure");
const comparison = await api("/api/runs/latest/comparison");

const browser = await chromium.launch(
  process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {},
);
const page = await browser.newPage();
const problems = [];
page.on("pageerror", (error) => problems.push(error.message));

async function open(path, waitFor) {
  await page.goto(`${BASE}${path}`);
  await page.locator("main").getByText(waitFor, { exact: false }).first().waitFor({ timeout: 15000 });
  const text = await page.locator("main").innerText();
  // Acceptance 1: no JSON on screen
  assert.ok(!/[{[]\s*"[a-z_]+"\s*:/.test(text), `${path} shows JSON`);
  return text;
}

const checks = [];
async function check(name, fn) {
  await fn();
  checks.push(name);
  console.log(`ok  ${name}`);
}

await check("overview reads like the run", async () => {
  const text = await open("/", overview.result);
  for (const words of [overview.verdict, overview.score.toFixed(2), "Findings"]) {
    assert.ok(text.includes(words), `overview lacks "${words}"`);
  }
  const lost = overview.losses.flatMap((side) => side.lost)[0];
  if (lost) {
    const sentence = `${lost.name} at tick ${lost.tick}, by ${lost.by_name}`;
    assert.ok(text.includes(sentence), `overview lacks "${sentence}"`);
  }
  await page.getByRole("img", { name: "Score on each evaluation axis" }).locator("svg").waitFor();
});

await check("the run picker names the service's runs (Phase 21)", async () => {
  const picker = page.getByLabel("Run");
  await picker.waitFor();
  assert.equal(await picker.inputValue(), newest.run);
  assert.equal(await picker.locator("option").count(), runs.length);
  await page.goto(`${BASE}/timeline/?run=${newest.run}`);
  await page.locator("section.tick").first().waitFor();
  const href = await page.getByRole("link", { name: "Overview" }).getAttribute("href");
  assert.equal(href, `/?run=${newest.run}`, "the pages lose the run");
});

await check("timeline shows every tick (acceptance 2)", async () => {
  const last = timeline.ticks[timeline.ticks.length - 1];
  await open("/timeline/", `Tick ${last.tick}`);
  assert.equal(await page.locator("section.tick").count(), timeline.ticks.length);
  const busy = timeline.ticks.find((tick) => tick.lines.length > 0);
  assert.ok((await page.locator("main").innerText()).includes(busy.lines[0]));
});

await check("replay steps tick by tick over the WebSocket (acceptance 2)", async () => {
  await open("/replay/", "Units in their starting positions");
  const world = page.locator("svg.world-map");
  assert.equal(await world.getAttribute("data-tick"), "0");
  assert.equal(await page.locator("g.unit").count(), map.frames[0].units.length);
  for (let tick = 1; tick <= 3; tick += 1) {
    await page.getByRole("button", { name: "Next" }).click();
    await page.locator(`svg.world-map[data-tick="${tick}"]`).waitFor();
  }
  const last = map.frames[map.frames.length - 1].tick;
  await page.getByRole("button", { name: "Play" }).click();
  await page.locator(`svg.world-map[data-tick="${last}"]`).waitFor({ timeout: 30000 });
});

await check("causal chain names who did what", async () => {
  const total = causal.chains.length;
  await open("/causal/", `${total} of ${total} actions`);
  const losses = causal.chains.filter((c) => c.event_types.includes("ENTITY_DESTROYED")).length;
  await page.getByLabel("Only actions that destroyed a unit").check();
  await page.getByText(`${losses} of ${total} actions`).waitFor();
});

await check("failure map shows survival by stress (acceptance 3)", async () => {
  const text = await open("/failure/", "Crushed by");
  const words = ["Recommended modifications", failure.levels[0]];
  if (failure.crushing_variable) words.push(failure.crushing_variable);
  for (const alternative of failure.alternatives) words.push(alternative.scenario_version);
  for (const expected of words) {
    assert.ok(text.includes(expected), `failure map lacks "${expected}"`);
  }
  assert.ok((await page.locator("td.heat").count()) > 0, "no survival cells");
});

await check("comparison puts plans side by side", async () => {
  const text = await open("/compare/", "Every variant");
  for (const variant of comparison.variants) {
    assert.ok(text.includes(variant.variant_id), `comparison lacks "${variant.variant_id}"`);
  }
});

await check("result package is labelled and collapsed", async () => {
  const text = await open("/package/", "Everything that happened");
  assert.ok(text.includes(`${overview.event_count} events`));
  await page.getByText("Everything that happened").click();
  const opened = page.locator("section", { hasText: "Everything that happened" }).locator("pre");
  assert.ok((await opened.innerText()).includes("event_id"));
});

await check("briefing downloads as PDF and Word (acceptance 4)", async () => {
  const text = await open("/report/", "SKYVAULT briefing");
  assert.ok(text.includes(overview.scenario_id));
  for (const [label, magic] of [
    ["Download PDF", "%PDF"],
    ["Download Word", "PK"],
  ]) {
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("link", { name: label }).click(),
    ]);
    const stream = await download.createReadStream();
    const chunks = [];
    for await (const chunk of stream) chunks.push(chunk);
    assert.ok(Buffer.concat(chunks).subarray(0, magic.length).toString() === magic, `${label} is not a file`);
  }
});

await check("no page is wider than a phone screen", async () => {
  const phone = await browser.newPage({ viewport: { width: 390, height: 844 } });
  for (const path of ["/", "/timeline/", "/replay/", "/causal/", "/failure/", "/compare/", "/package/", "/report/"]) {
    await phone.goto(`${BASE}${path}`);
    await phone.locator("main h1").first().waitFor();
    await phone.waitForLoadState("networkidle");
    const width = await phone.evaluate(() => document.documentElement.scrollWidth);
    assert.ok(width <= 390, `${path} is ${width}px wide on a 390px screen`);
  }
  await phone.close();
});

await browser.close();
assert.deepEqual(problems, [], `page errors: ${problems.join("; ")}`);
console.log(`${checks.length} checks passed`);
