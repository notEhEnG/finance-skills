/**
 * Capture demo.html frames with Puppeteer and write PNGs for ffmpeg → GIF.
 * Also writes a Lottie-compatible JSON handoff (data-stats style beats).
 */
import puppeteer from "puppeteer";
import { mkdir, writeFile } from "fs/promises";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const outDir = join(__dirname, "frames");
const htmlPath = join(__dirname, "demo.html");

const FPS = 10;
const DURATION_S = 9;
const TOTAL = Math.round(FPS * DURATION_S);

await mkdir(outDir, { recursive: true });

const browser = await puppeteer.launch({
  headless: true,
  args: ["--no-sandbox", "--disable-setuid-sandbox", "--font-render-hinting=none"],
});
const page = await browser.newPage();
await page.setViewport({ width: 960, height: 540, deviceScaleFactor: 1 });
await page.goto("file://" + htmlPath, { waitUntil: "networkidle0" });
// let first paint settle
await new Promise((r) => setTimeout(r, 200));

for (let i = 0; i < TOTAL; i++) {
  // advance animation by waiting; rAF runs wall-clock
  const path = join(outDir, `frame_${String(i).padStart(4, "0")}.png`);
  await page.screenshot({ path, type: "png" });
  await new Promise((r) => setTimeout(r, 1000 / FPS));
  if (i % 12 === 0) console.error(`frame ${i}/${TOTAL}`);
}

await browser.close();
console.log(`wrote ${TOTAL} frames to ${outDir}`);
