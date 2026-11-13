// Optional browser smoke test. Requires Playwright and a running RelayBench server.
const {chromium} = require("playwright");
const assert = require("node:assert/strict");

async function main() {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({viewport: {width: 1280, height: 1080}, deviceScaleFactor: 1});
    const errors = [];
    page.on("pageerror", e => errors.push(e.message));
    await page.goto(process.env.RELAYBENCH_URL || "http://127.0.0.1:8765");
    await page.getByRole("button", {name: "Run experiment"}).click();
    await page.getByText("Passed", {exact:true}).waitFor();
    await page.getByRole("button", {name: "Compare policies"}).click();
    await page.getByText(/First different decision at step 3/).waitFor();
    await page.getByRole("button", {name: "Verify replay"}).click();
    await page.getByText(/Verified all 4 transitions/).waitFor();
    await page.screenshot({path: process.env.RELAYBENCH_SCREENSHOT || "docs/demo.png", fullPage:true});
    await page.setViewportSize({width: 390, height: 844});
    await page.getByRole("button", {name:/Blind retry · 42/}).first().click();
    await page.getByText("Failed", {exact:true}).waitFor();
    await page.locator("summary").nth(1).click();
    assert.equal(await page.locator("details[open]").count(), 1);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert.deepEqual(errors, []);
  } finally {
    await browser.close();
  }
}
main().catch(error => {console.error(error); process.exitCode = 1;});
