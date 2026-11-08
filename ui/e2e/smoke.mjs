/**
 * Browser smoke test for the reference workspace (Phase 17 acceptance).
 *
 *   SKYVAULT_URL=http://127.0.0.1:8000 node e2e/smoke.mjs
 *
 * Opens every page in Chromium and checks that it shows sentences and
 * tables a person can read, not JSON: the timeline tick by tick, the replay
 * stepping, the failure map, the comparison, and both briefing downloads.
 * CHROMIUM_PATH points at a browser binary when Playwright's own is absent.
 */

import assert from "node:assert/strict";
import { chromium } from "playwright";

const BASE = process.env.SKYVAULT_URL ?? "http://127.0.0.1:8000";
const browser = await chromium.launch(
  process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {},
);
const page = await browser.newPage();
const problems = [];
page.on("pageerror", (error) => problems.push(error.message));

async function open(path, waitFor) {
  await page.goto(`${BASE}${path}`);
  await page.getByText(waitFor, { exact: false }).first().waitFor({ timeout: 15000 });
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
  const text = await open("/", "RED_survived");
  for (const words of ["risky", "0.50", "Red Commander at tick 6, by Blue Support", "Findings"]) {
    assert.ok(text.includes(words), `overview lacks "${words}"`);
  }
  await page.getByRole("img", { name: "Score on each evaluation axis" }).locator("svg").waitFor();
});

await check("timeline shows every tick (acceptance 2)", async () => {
  const text = await open("/timeline/", "Tick 10");
  assert.equal(await page.locator("section.tick").count(), 10);
  assert.ok(text.includes("Blue Commander in the BLUE faction was destroyed by Red Rifleman"));
  assert.equal(await page.locator("#tick-6 li.destroyed").count(), 2);
});

await check("replay steps tick by tick over the WebSocket (acceptance 2)", async () => {
  await open("/replay/", "Units in their starting positions");
  const map = page.locator("svg.world-map");
  assert.equal(await map.getAttribute("data-tick"), "0");
  assert.equal(await page.locator("g.unit").count(), 6);
  for (let tick = 1; tick <= 6; tick += 1) {
    await page.getByRole("button", { name: "Next" }).click();
    await page.locator(`svg.world-map[data-tick="${tick}"]`).waitFor();
  }
  assert.equal(await page.locator('g.unit[data-unit="red_003"]').getAttribute("data-status"), "destroyed");
  assert.ok((await page.locator("main").innerText()).includes("Red Commander in the RED faction was destroyed"));
  await page.getByRole("button", { name: "Play" }).click();
  await page.locator('svg.world-map[data-tick="10"]').waitFor({ timeout: 15000 });
});

await check("causal chain names who did what", async () => {
  const text = await open("/causal/", "Red Rifleman");
  assert.ok(text.includes("46 of 46 actions"));
  await page.getByLabel("Only actions that destroyed a unit").check();
  await page.getByText("4 of 46 actions").waitFor();
});

await check("failure map shows survival by stress (acceptance 3)", async () => {
  const text = await open("/failure/", "Crushed by");
  for (const words of ["communication_failure", "v0.1-support-rear", "60%", "Recommended modifications"]) {
    assert.ok(text.includes(words), `failure map lacks "${words}"`);
  }
  const row = page.locator("tr", { hasText: "communication failure" });
  assert.deepEqual(await row.locator("td.heat").allInnerTexts(), ["70%", "80%", "50%", "0%"]);
});

await check("comparison puts plans and branches side by side", async () => {
  const text = await open("/compare/", "Every variant");
  for (const words of ["support-rear", "branch:P2+P3", "Decision required: yes", "no orders"]) {
    assert.ok(text.includes(words), `comparison lacks "${words}"`);
  }
});

await check("result package is labelled and collapsed", async () => {
  const text = await open("/package/", "Everything that happened");
  assert.ok(text.includes("97 events"));
  await page.getByText("Everything that happened").click();
  const opened = page.locator("section", { hasText: "Everything that happened" }).locator("pre");
  assert.ok((await opened.innerText()).includes("event_id"));
});

await check("briefing downloads as PDF and Word (acceptance 4)", async () => {
  const text = await open("/report/", "SKYVAULT briefing");
  assert.ok(text.includes("Survives without stress: 60%"));
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
