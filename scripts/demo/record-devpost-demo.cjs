const fs = require('fs');
const { chromium } = require(
  '/home/kadirerenaltintas/.npm/_npx/e41f203b7505f1fb/node_modules/playwright',
);

const baseUrl = 'http://127.0.0.1:8126';
const root = '/home/kadirerenaltintas/claimgate';
const rawPath = `${root}/artifacts/claimgate-devpost-demo-raw.webm`;
const timingPath = `${root}/artifacts/claimgate-devpost-demo-timing.json`;
const errorPath = `${root}/artifacts/claimgate-devpost-demo-error.log`;
const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
let browser;

async function decorate(page) {
  await page.evaluate(() => {
    document.querySelector('#cg-demo-style')?.remove();
    document.querySelector('#cg-demo-cursor')?.remove();
    document.querySelector('#cg-demo-caption')?.remove();
    const style = document.createElement('style');
    style.id = 'cg-demo-style';
    style.textContent = `
      #cg-demo-cursor { position: fixed; z-index: 2147483647; width: 23px; height: 23px;
        pointer-events: none; transform: translate(-4px,-3px) rotate(-18deg); transition: none;
        filter: drop-shadow(0 2px 3px rgba(0,0,0,.35)); }
      #cg-demo-cursor::before { content: ''; display:block; width:0; height:0;
        border-left: 8px solid transparent; border-right: 8px solid transparent;
        border-bottom: 22px solid #ff5c35; }
      #cg-demo-cursor.pulse::after { content:''; position:absolute; left:-8px; top:-7px;
        width:34px; height:34px; border:2px solid rgba(255,92,53,.75); border-radius:50%;
        animation: cgPulse .45s ease-out; }
      @keyframes cgPulse { from { transform:scale(.25); opacity:1 } to { transform:scale(1.45); opacity:0 } }
      #cg-demo-caption { position:fixed; left:50%; bottom:32px; transform:translateX(-50%);
        z-index:2147483646; max-width:1320px; padding:14px 26px; border-radius:14px;
        color:#fff; background:rgba(15,23,42,.92); box-shadow:0 12px 34px rgba(15,23,42,.25);
        font:600 25px/1.25 Inter,ui-sans-serif,system-ui,sans-serif; letter-spacing:-.01em;
        text-align:center; pointer-events:none; border:1px solid rgba(255,255,255,.18); }
    `;
    document.head.append(style);
    const cursor = document.createElement('div');
    cursor.id = 'cg-demo-cursor';
    cursor.style.left = '800px';
    cursor.style.top = '450px';
    const caption = document.createElement('div');
    caption.id = 'cg-demo-caption';
    document.body.append(cursor, caption);
    document.addEventListener('mousemove', (event) => {
      cursor.style.left = `${event.clientX}px`;
      cursor.style.top = `${event.clientY}px`;
    });
    document.addEventListener('click', () => {
      cursor.classList.remove('pulse');
      void cursor.offsetWidth;
      cursor.classList.add('pulse');
    });
  });
}

async function caption(page, text) {
  await page.locator('#cg-demo-caption').evaluate((element, value) => {
    element.textContent = value;
  }, text);
}

async function smoothMove(page, target, steps = 32) {
  const box = typeof target === 'string'
    ? await page.locator(target).first().boundingBox()
    : await target.boundingBox();
  if (!box) throw new Error(`Cannot move to invisible target: ${target}`);
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps });
  await sleep(350);
}

async function clickTarget(page, target) {
  const locator = typeof target === 'string' ? page.locator(target).first() : target;
  await smoothMove(page, locator);
  await locator.click();
  await sleep(450);
}

(async () => {
  fs.rmSync(errorPath, { force: true });
  browser = await chromium.launch({ headless: true });

  // Create a local-only account outside the recording so no credentials appear in any frame.
  const authContext = await browser.newContext({ viewport: { width: 1600, height: 900 } });
  const authPage = await authContext.newPage();
  await authPage.goto(`${baseUrl}/signup`, { waitUntil: 'networkidle' });
  await authPage.locator('#signup-full-name').fill('ClaimGate Demo Operator');
  await authPage.locator('#signup-email').fill(`devpost-${Date.now()}@claimgate.local`);
  await authPage.locator('#signup-workspace').fill('Asterion Procurement');
  await authPage.locator('#signup-password').fill('LocalDemoOnly2026!');
  await authPage.locator('#signup-confirm-password').fill('LocalDemoOnly2026!');
  await Promise.all([
    authPage.waitForURL('**/app'),
    authPage.locator('#signup-submit').click(),
  ]);
  const storageState = await authContext.storageState();
  await authContext.close();

  const context = await browser.newContext({
    viewport: { width: 1600, height: 900 },
    storageState,
    bypassCSP: true,
    recordVideo: { dir: `${root}/artifacts`, size: { width: 1600, height: 900 } },
  });
  const page = await context.newPage();
  const video = page.video();
  const startedAt = Date.now();
  const timing = {};
  const elapsed = () => (Date.now() - startedAt) / 1000;

  page.on('pageerror', (error) => process.stderr.write(`browser page error: ${error.message}\n`));

  await page.goto(baseUrl, { waitUntil: 'networkidle' });
  await decorate(page);
  await caption(page, 'AI can propose. It should not authorize itself.');
  await smoothMove(page, '.landing-hero-copy-block');
  await sleep(6800);

  await page.goto(`${baseUrl}/app`, { waitUntil: 'networkidle' });
  await decorate(page);
  await caption(page, 'ClaimGate sits between AI reasoning and irreversible execution.');
  await smoothMove(page, '#page-overview');
  await sleep(8000);

  await clickTarget(page, 'a[data-page="workflows"]');
  await caption(page, 'A supplier contract is ready for signing.');
  await page.locator('#start-workflow').scrollIntoViewIfNeeded();
  await smoothMove(page, '#artifact-dropzone');
  await page.locator('#artifact-file-input').setInputFiles(
    `${root}/ClaimGate_Demo_Procurement_Agreement_CONFLICT.pdf`,
  );
  await sleep(9000);

  await caption(page, 'Internal approval says: USD 15,000.');
  await clickTarget(page, '#add-evidence-button');
  const evidenceRow = page.locator('.evidence-input-row').last();
  await evidenceRow.locator('.evidence-input-title').fill(
    'Procurement Approval Record PR-2026-441',
  );
  await evidenceRow.locator('.evidence-input-file').setInputFiles(
    `${root}/ClaimGate_Demo_Authoritative_Evidence.txt`,
  );
  await evidenceRow.scrollIntoViewIfNeeded();
  await smoothMove(page, evidenceRow);
  await sleep(9000);

  await caption(
    page,
    'Foxit extracts the real PDF. AI identifies material claims. Deterministic policy decides authorization.',
  );
  timing.processingStart = elapsed();
  await clickTarget(page, '#generate-button');
  await page.waitForURL(/\/app\/workflows\/[a-f0-9]+/, { timeout: 30_000 });
  const progressTargets = page.locator('#progress-steps .progress-step');
  for (let iteration = 0; iteration < 80; iteration += 1) {
    const finished = await page.locator('#result-view').isVisible().catch(() => false);
    if (finished) break;
    const count = await progressTargets.count();
    if (count) {
      try {
        await smoothMove(page, progressTargets.nth(iteration % count), 24);
      } catch (error) {
        if (await page.locator('#result-view').isVisible().catch(() => false)) break;
        throw error;
      }
    }
    await sleep(5000);
  }
  await page.locator('#result-view').waitFor({ state: 'visible', timeout: 600_000 });
  timing.processingEnd = elapsed();

  const moneyCard = page.locator('.claim-card').filter({ hasText: 'USD 12,500.00' }).filter({ hasText: 'CONFLICTING' }).first();
  const resultChecks = await page.evaluate(() => ({
    decision: document.querySelector('#decision-label')?.textContent || '',
    explanation: document.querySelector('#decision-explanation')?.textContent || '',
    approvalHidden: document.querySelector('#approval-panel')?.hidden,
    receipt: document.querySelector('#structured-receipt-json')?.textContent || '',
    claims: [...document.querySelectorAll('.claim-card')].map((card) => card.innerText),
  }));
  const moneyCardCount = await moneyCard.count();
  const diagnostic = JSON.stringify({ ...resultChecks, receipt: resultChecks.receipt.slice(0, 4000), moneyCardCount }, null, 2);
  if (!/Blocked by deterministic policy/i.test(resultChecks.decision)) {
    throw new Error(`Unexpected live decision:\n${diagnostic}`);
  }
  if (!resultChecks.approvalHidden) throw new Error(`Approval controls were exposed for blocked run:\n${diagnostic}`);
  if (moneyCardCount !== 1) throw new Error(`Live USD 12,500 money conflict is missing:\n${diagnostic}`);
  if (!resultChecks.receipt.includes('CRITICAL_CLAIM_CONFLICTING')) {
    throw new Error(`Receipt does not include CRITICAL_CLAIM_CONFLICTING:\n${diagnostic}`);
  }

  await caption(page, 'SIGNING BLOCKED');
  await page.locator('#decision-banner').scrollIntoViewIfNeeded();
  await smoothMove(page, '#decision-banner');
  await sleep(6000);

  await clickTarget(page, '[data-detail-tab="evidence"]');
  await caption(page, 'Contract: $12,500   Approved: $15,000');
  await moneyCard.scrollIntoViewIfNeeded();
  await clickTarget(page, moneyCard);
  await sleep(11000);

  await clickTarget(page, '[data-detail-tab="policy"]');
  await caption(page, 'A critical money conflict closes the authorization boundary.');
  await page.locator('.policy-layers-panel').scrollIntoViewIfNeeded();
  await sleep(6500);

  await clickTarget(page, '[data-detail-tab="audit"]');
  await caption(page, 'The decision is bound to the exact artifact, evidence, policy, and action.');
  await page.locator('#receipt-panel').scrollIntoViewIfNeeded();
  await clickTarget(page, '#verify-receipt-button');
  await page.locator('#receipt-verification').waitFor({ state: 'visible', timeout: 30_000 });
  await sleep(8500);

  await page.goto(baseUrl, { waitUntil: 'networkidle' });
  await decorate(page);
  await caption(page, 'AI can propose. ClaimGate verifies. Humans authorize. Backends execute.');
  await smoothMove(page, '.brand-lockup');
  await sleep(9000);

  timing.rawEnd = elapsed();
  timing.runUrl = page.url();
  await page.close();
  await context.close();
  await video.saveAs(rawPath);
  fs.writeFileSync(timingPath, `${JSON.stringify(timing, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify({ rawPath, timingPath, timing }, null, 2)}\n`);
  await browser.close();
})().catch((error) => {
  const report = `${error.stack || error}\n`;
  fs.writeFileSync(errorPath, report);
  process.stderr.write(report);
  process.exitCode = 1;
}).finally(async () => {
  await browser?.close().catch(() => {});
});
