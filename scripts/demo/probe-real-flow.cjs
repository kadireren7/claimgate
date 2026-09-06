const { chromium } = require('/home/kadirerenaltintas/.npm/_npx/e41f203b7505f1fb/node_modules/playwright');

const baseUrl = 'http://127.0.0.1:8126';
const root = '/home/kadirerenaltintas/claimgate';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1600, height: 900 } });
  const page = await context.newPage();
  page.on('console', (message) => {
    if (message.type() === 'error') process.stderr.write(`browser console: ${message.text()}\n`);
  });
  page.on('pageerror', (error) => process.stderr.write(`browser page error: ${error.message}\n`));

  const probeEmail = `demo-${Date.now()}@claimgate.local`;
  await page.goto(`${baseUrl}/signup`, { waitUntil: 'networkidle' });
  await page.locator('#signup-full-name').fill('ClaimGate Demo Operator');
  await page.locator('#signup-email').fill(probeEmail);
  await page.locator('#signup-workspace').fill('Asterion Procurement');
  await page.locator('#signup-password').fill('LocalDemoOnly2026!');
  await page.locator('#signup-confirm-password').fill('LocalDemoOnly2026!');
  await Promise.all([
    page.waitForURL('**/app'),
    page.locator('#signup-submit').click(),
  ]);

  await page.goto(`${baseUrl}/app/workflows#start-workflow`, { waitUntil: 'networkidle' });
  await page.locator('#artifact-file-input').setInputFiles(`${root}/ClaimGate_Demo_Procurement_Agreement_CONFLICT.pdf`);
  await page.locator('#add-evidence-button').click();
  const evidenceRow = page.locator('.evidence-input-row').last();
  await evidenceRow.locator('.evidence-input-title').fill('Procurement Approval Record PR-2026-441');
  await evidenceRow.locator('.evidence-input-file').setInputFiles(`${root}/ClaimGate_Demo_Authoritative_Evidence.txt`);
  await page.locator('#generate-button').waitFor({ state: 'visible' });
  if (await page.locator('#generate-button').isDisabled()) throw new Error('Verify button remained disabled');
  await page.locator('#generate-button').click();
  await page.waitForURL(/\/app\/workflows\/[a-f0-9]+/, { timeout: 30_000 });

  await page.locator('#decision-label').waitFor({ state: 'visible', timeout: 600_000 });
  await page.waitForFunction(() => {
    const text = document.querySelector('#decision-label')?.textContent?.trim();
    return text && !/loading/i.test(text);
  }, null, { timeout: 600_000 });

  const result = await page.evaluate(() => ({
    url: location.pathname,
    decision: document.querySelector('#decision-label')?.textContent?.trim(),
    explanation: document.querySelector('#decision-explanation')?.textContent?.trim(),
    status: document.querySelector('#workflow-header-status')?.textContent?.trim(),
    claims: [...document.querySelectorAll('.claim-card')].map((card) => card.innerText),
    receipt: document.querySelector('#receipt-panel')?.innerText,
    approvalHidden: document.querySelector('#approval-panel')?.hidden,
  }));
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  await page.screenshot({ path: `${root}/artifacts/demo-probe-result.png`, fullPage: true });
  await browser.close();
})().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
