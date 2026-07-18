// Screenshot van het Corp Hauling-bord. Logt in via de Django-admin (die
// gebruikt gewoon wachtwoord-login); de sessie geldt daarna voor de hele site.
import { chromium } from 'playwright-core'
import fs from 'fs'

const AUTH = process.env.AUTH_URL ?? 'http://localhost:8000'
const USER = process.env.AUTH_USER ?? 'admin'
const PASS = process.env.AUTH_PASS ?? 'adminLocal123!'
const SHOT = new URL('../.shots/', import.meta.url).pathname.replace(/^\/(\w:)/, '$1')
fs.mkdirSync(SHOT, { recursive: true })

const browser = await chromium.launch({ channel: 'msedge', headless: true })
const ctx = await browser.newContext({ viewport: { width: 1500, height: 950 } })
const page = await ctx.newPage()
page.on('pageerror', e => console.log('PAGE ERROR:', e.message))

console.log('inloggen…')
await page.goto(`${AUTH}/admin/login/?next=/corp-hauling/`, { waitUntil: 'domcontentloaded' })
await page.fill('#id_username', USER)
await page.fill('#id_password', PASS)
await page.click('input[type=submit]')
await page.waitForLoadState('domcontentloaded')
await page.waitForTimeout(1500)

console.log('url na login:', page.url())
await page.screenshot({ path: SHOT + 'bord.png', fullPage: true })

// Alleen de route-cel van de eerste rij, uitvergroot
const cel = page.locator('table.cc-table tbody tr td').first()
if (await cel.count()) {
  await cel.screenshot({ path: SHOT + 'route-cel.png' })
  console.log('route-cel:', (await cel.innerText()).replace(/\n/g, ' | '))
}

const tabel = page.locator('table.cc-table')
if (await tabel.count()) await tabel.screenshot({ path: SHOT + 'tabel.png' })

console.log('screenshots in', SHOT)
await browser.close()
