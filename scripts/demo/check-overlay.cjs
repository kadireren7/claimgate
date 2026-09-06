const { chromium } = require(
  '/home/kadirerenaltintas/.npm/_npx/e41f203b7505f1fb/node_modules/playwright',
);

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1600, height: 900 },
    bypassCSP: true,
  });
  const page = await context.newPage();
  await page.goto('http://127.0.0.1:8126/', { waitUntil: 'networkidle' });
  await page.evaluate(() => {
    const style = document.createElement('style');
    style.textContent = `
      #cg-demo-cursor { position: fixed; z-index: 2147483647; width: 23px; height: 23px;
        pointer-events: none; left: 800px; top: 450px; background: #ff5c35; }
      #cg-demo-caption { position:fixed; left:50%; bottom:32px; transform:translateX(-50%);
        z-index:2147483646; padding:14px 26px; color:#fff; background:#0f172a;
        font:600 25px/1.25 sans-serif; }
    `;
    document.head.append(style);
    const cursor = document.createElement('div');
    cursor.id = 'cg-demo-cursor';
    const caption = document.createElement('div');
    caption.id = 'cg-demo-caption';
    caption.textContent = 'Overlay visibility check';
    document.body.append(cursor, caption);
  });
  const state = await page.locator('#cg-demo-caption').evaluate((element) => ({
    rect: element.getBoundingClientRect().toJSON(),
    display: getComputedStyle(element).display,
    visibility: getComputedStyle(element).visibility,
    opacity: getComputedStyle(element).opacity,
  }));
  await page.screenshot({ path: 'artifacts/overlay-check.png' });
  process.stdout.write(`${JSON.stringify(state)}\n`);
  await browser.close();
})().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
