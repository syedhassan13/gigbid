// node scripts/html_to_pdf.mjs <in.html> <out.pdf>  (uses the Playwright Chromium installed for e2e tests)
import { chromium } from "../apps/web/node_modules/@playwright/test/index.mjs";
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";
const [, , inp, out] = process.argv;
const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto(pathToFileURL(resolve(inp)).href, { waitUntil: "networkidle" });
await page.pdf({ path: out, format: "A4", margin: { top: "16mm", bottom: "16mm", left: "15mm", right: "15mm" }, printBackground: true,
  displayHeaderFooter: true, headerTemplate: "<div></div>",
  footerTemplate: '<div style="font-size:8px;width:100%;text-align:center;color:#666">GigBid R&D report · page <span class="pageNumber"></span> / <span class="totalPages"></span></div>' });
await browser.close();
console.log("wrote", out, readFileSync(out).length, "bytes");
