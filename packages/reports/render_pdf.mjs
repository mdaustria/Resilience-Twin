import { readFile, writeFile } from 'node:fs/promises';
import { chromium } from '@playwright/test';

const [input, output] = process.argv.slice(2);
if (!input || !output) throw new Error('Usage: node render_pdf.mjs input.html output.pdf');
const html = await readFile(input, 'utf8');
const browser = await chromium.launch({ headless: true });
try {
  const context = await browser.newContext({ javaScriptEnabled: false, offline: true });
  await context.route('**/*', (route) => route.abort());
  const page = await context.newPage();
  await page.setContent(html, { waitUntil: 'load' });
  const pdf = await page.pdf({ format: 'A4', printBackground: true });
  await writeFile(output, pdf);
  await context.close();
} finally {
  await browser.close();
}
