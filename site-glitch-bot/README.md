# Site Glitch Bot

Apni websites ka "glitch hunter". Yeh bot aapki site ko ek asli Chromium browser
mein khol kar har page par jata hai, links follow karta hai, aur jo kuch bhi toota
hua ho uski list ek saaf HTML report mein de deta hai.

A crawler that opens your own website in a real browser, follows every internal
link and reports everything that looks broken.

## Kya kya pakarta hai / What it catches

| Severity | Glitch |
|---|---|
| Critical | Pages returning 404 / 500, pages that won't load, uncaught JavaScript errors, broken images/CSS/JS on your own domain, broken links to PDFs and other files, https → http downgrade |
| Warning | Console errors, slow pages, sideways scrolling on mobile (names the element that's too wide), mixed content, redirect chains, soft-404s, blank pages, `undefined` / `NaN` / `[object Object]` / `{{ }}` / PHP errors / stack traces / lorem ipsum showing on the page, missing `<title>` or viewport tag, duplicate titles, broken external links (optional) |
| Info | Missing meta description / `<h1>`, images without alt, form fields without labels, duplicate ids, links that go nowhere |

### Deep scan (on by default)

On every page the bot also:

- **Scrolls to the bottom**, so lazy-loaded images and sections are checked too.
- **Clicks every safe button, menu, tab and accordion** and reports JavaScript
  errors that only happen after a click (`JavaScript error after clicking "Menu"`).
  Pages that open only from a button (no normal link) are found and scanned.
  It never clicks anything like Delete, Buy, Checkout, Pay, Submit, Logout or
  Sign up, and it blocks every form send/POST while clicking, so no data changes.
- **Measures speed like Google does:** when the main content appears (LCP),
  how much the page jumps while loading (layout shift), how long it freezes,
  total download size, and heavy images/scripts.
- **Checks phone and tablet** widths: sideways scrolling, text cut off, buttons
  too small to tap.
- **Accessibility** (axe-core): unreadable low-contrast text, missing labels, etc.
- **SEO:** noindex left on by mistake, wrong canonical, missing share previews,
  links to `#sections` that don't exist.
- **Whole-site security checks, once per site:** SSL certificate expiry,
  http → https redirect, security headers, server version leaks, old jQuery,
  and publicly exposed files like `.env`, `.git`, database dumps and open folder
  listings.

The worst problems are also printed in the terminal at the end.

Use `--quick` for the old fast surface scan, `--max-clicks 0` to scan deeply
without clicking, and `--urls pages.txt` to add pages the bot can't reach by
itself (one URL per line).

Every broken page shows **which pages link to it**, and pages with critical
problems get a screenshot.

## Update

Latest version lene ke liye (bina git, bina ZIP):

```bash
node update.js
```

It downloads only the files that changed from GitHub and keeps your reports.

## Windows (PowerShell)

1. Install Node.js LTS from https://nodejs.org (then close and reopen PowerShell).
2. Open the `site-glitch-bot` folder in PowerShell and run:

```powershell
.\scan.cmd
```

It asks for the website link, installs everything on the first run and opens
the report when it's done. You can also double-click `scan.cmd`, or pass
options directly:

```powershell
.\scan.cmd https://yoursite.com --max-pages 2000 --exclude "logout|/cart"
```

If you run `npm` yourself and PowerShell says *"running scripts is disabled on
this system"*, use `npm.cmd` / `npx.cmd` instead, or allow scripts once with
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## Setup (Mac / Linux)

```bash
cd site-glitch-bot
npm install
npx playwright install chromium   # only if Chromium isn't installed yet
```

## Chalana / Usage

```bash
node bot.js https://yoursite.com
```

Report: `glitch-report/report.html` (browser mein kholein) and `glitch-report/report.json`.

Useful options for big sites:

```bash
# 2000 pages, 6 at a time, external links bhi check karo
node bot.js https://yoursite.com --max-pages 2000 --concurrency 6 --check-external

# Sirf /shop wale pages, logout aur cart chhor do
node bot.js https://yoursite.com --include "/shop" --exclude "logout|/cart"
```

Run `node bot.js --help` for all options.

- The bot seeds from `/sitemap.xml`, respects `robots.txt` (`--ignore-robots`
  to override on your own site), strips `utm_*`/`fbclid` params, and stays on
  your domain (www and non-www count as the same site).
- It doesn't submit forms or click buttons, so it won't place orders or change data.
- Defaults are gentle (4 pages in parallel, 250 ms pause each). On a large
  production site raise `--concurrency` gradually and watch server load.
- Only scan sites you own or have permission to test.

## CI / scheduled runs

The exit code is `1` when critical issues are found (`--fail-on warning` to be
stricter, `--fail-on none` to never fail), so it can run in GitHub Actions or a
nightly cron and fail the build when something breaks.

## Test

```bash
npm test
```

Spins up a small local site with planted glitches (404, 500, JS error, broken
image, mobile overflow, leaked `undefined`, missing PDF, robots-blocked page) and
checks the bot finds every one.
