// Build-time prerendering for the public marketing pages - visits each public route against the
// freshly built app (served locally, pointed at the real production API) with a headless browser,
// waits for the client-side fetch+render to settle, and writes the resulting DOM as a static
// index.html at the matching path. nginx's existing try_files directory-index mechanism then
// serves these directly, so a crawler that doesn't execute JS still sees real content.
//
// Deliberately best-effort: this is an SEO enhancement, not a build requirement. Any failure here
// (missing PRODUCTION_URL, sitemap unreachable, a single page erroring) is logged and the script
// still exits 0 - a deploy must never fail just because prerendering didn't work this time. See
// ../../.claude/plans (or the PR that introduced this) for the full design rationale, in
// particular why the homepage's own dist/index.html gets overwritten while dist/app-shell.html
// (a copy of the pristine pre-render build) becomes nginx's new SPA fallback target instead.

import { spawn } from 'node:child_process'
import { mkdir, copyFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '@playwright/test'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const FRONTEND_ROOT = path.resolve(__dirname, '..')
const DIST_DIR = path.join(FRONTEND_ROOT, 'dist')
const PREVIEW_PORT = 4173
const PREVIEW_ORIGIN = `http://localhost:${PREVIEW_PORT}`

function warn(message) {
  console.warn(`::warning::prerender: ${message}`)
}

async function fetchSitemapPaths(productionUrl) {
  const sitemapUrl = `${productionUrl.replace(/\/$/, '')}/sitemap.xml`
  const attempts = 5
  let lastError
  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      const response = await fetch(sitemapUrl)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const xml = await response.text()
      const locs = [...xml.matchAll(/<loc>(.*?)<\/loc>/g)].map((m) => m[1])
      if (!locs.length) throw new Error('sitemap.xml had no <loc> entries')
      // The host in each <loc> comes from Django's own FRONTEND_URL env var, which isn't
      // guaranteed to be byte-identical to PRODUCTION_URL here, and it's irrelevant anyway -
      // this script always crawls the locally served preview build, never the live domain.
      return locs.map((loc) => new URL(loc).pathname)
    } catch (err) {
      lastError = err
      // The backend container is restarted (`docker run -d`) just before the frontend build
      // steps in the same CI job - that returns before gunicorn inside is actually accepting
      // connections, so an early sitemap fetch can genuinely race a cold start.
      if (attempt < attempts) await new Promise((r) => setTimeout(r, attempt * 2000))
    }
  }
  throw lastError
}

function waitForPreviewServer() {
  const deadline = Date.now() + 30_000
  return new Promise((resolve, reject) => {
    const poll = async () => {
      try {
        const response = await fetch(PREVIEW_ORIGIN)
        if (response.ok || response.status < 500) return resolve()
      } catch {
        // Not up yet - keep polling until the deadline.
      }
      if (Date.now() > deadline) return reject(new Error('vite preview never became ready'))
      setTimeout(poll, 500)
    }
    poll()
  })
}

// previewProcess.kill() alone only signals the shell spawn() created (shell: true), not the
// npx/node/vite descendants it launched - left as-is, that leaks an orphaned vite preview server
// holding the port (and, in CI, the runner) open after this script exits. On POSIX, spawning
// detached puts the whole tree in its own process group, killable in one shot via the negative
// PID; Windows has no such concept, so taskkill's own /t (tree) flag does the equivalent.
function killProcessTree(child) {
  if (process.platform === 'win32') {
    spawn('taskkill', ['/pid', String(child.pid), '/t', '/f'])
  } else {
    try {
      process.kill(-child.pid)
    } catch {
      child.kill()
    }
  }
}

function outputPathFor(routePath) {
  if (routePath === '/') return path.join(DIST_DIR, 'index.html')
  return path.join(DIST_DIR, routePath.replace(/^\//, ''), 'index.html')
}

async function main() {
  const productionUrl = process.env.PRODUCTION_URL
  if (!productionUrl) {
    warn('PRODUCTION_URL is not set - skipping prerender entirely.')
    return
  }

  try {
    // Must happen before anything overwrites dist/index.html - this pristine copy becomes
    // nginx's new SPA fallback target (see deploy/nginx/silverlake.conf's try_files change) for
    // every gated/unmatched route, so they keep getting a neutral empty shell instead of a flash
    // of prerendered homepage content.
    await copyFile(path.join(DIST_DIR, 'index.html'), path.join(DIST_DIR, 'app-shell.html'))
  } catch (err) {
    warn(`could not copy dist/index.html to app-shell.html (${err.message}) - was "npm run build" run first? Skipping prerender.`)
    return
  }

  let routePaths
  try {
    routePaths = await fetchSitemapPaths(productionUrl)
  } catch (err) {
    warn(`could not fetch sitemap.xml after retries (${err.message}) - skipping prerender.`)
    return
  }

  // shell: true - `npx` is a .cmd shim on Windows, not something spawn() can exec directly by
  // name the way it can on POSIX; this keeps the script runnable both on a Linux CI runner and
  // locally on Windows for the "test it before trusting CI" verification step. The whole command
  // is passed as one string (not command + args array) - Node warns/deprecates that combination
  // with shell: true, since args would otherwise be concatenated unescaped; there's no untrusted
  // input here (every value is a hardcoded constant), but the single-string form sidesteps the
  // warning entirely rather than relying on that being safe.
  const previewProcess = spawn(`npx vite preview --port ${PREVIEW_PORT} --strictPort`, {
    cwd: FRONTEND_ROOT,
    stdio: 'ignore',
    shell: true,
    detached: process.platform !== 'win32',
  })

  let browser
  let succeeded = 0
  try {
    await waitForPreviewServer()
    browser = await chromium.launch()

    for (const routePath of routePaths) {
      try {
        const page = await browser.newPage()
        // Flags this page to main.js so analytics/error-tracking/push-notification registration
        // stay off for the crawl - see main.js's own window.__PRERENDERING__ check.
        await page.addInitScript(() => {
          window.__PRERENDERING__ = true
        })
        await page.goto(`${PREVIEW_ORIGIN}${routePath}`, { waitUntil: 'networkidle', timeout: 15_000 })
        await page.waitForTimeout(300)
        let html = await page.content()
        await page.close()

        // utils/seo.js's setPageMeta() builds the canonical link/og:url from
        // window.location.origin, which during this crawl is the local preview server, not the
        // real site - on an actual visitor's browser this is correct (they really are at
        // PRODUCTION_URL), so the fix belongs here (post-processing the captured snapshot), not
        // in seo.js itself.
        html = html.split(PREVIEW_ORIGIN).join(productionUrl.replace(/\/$/, ''))

        const outputPath = outputPathFor(routePath)
        await mkdir(path.dirname(outputPath), { recursive: true })
        await writeFile(outputPath, html)
        succeeded++
      } catch (err) {
        warn(`failed to prerender ${routePath}: ${err.message}`)
      }
    }
  } catch (err) {
    warn(`prerender run failed before completing: ${err.message}`)
  } finally {
    if (browser) await browser.close()
    killProcessTree(previewProcess)
  }

  if (succeeded === 0) {
    warn(`prerendered 0 of ${routePaths?.length ?? 0} pages - something is systemically broken, check the log above.`)
  } else {
    console.log(`prerender: wrote ${succeeded} of ${routePaths.length} pages.`)
  }
}

main().catch((err) => {
  // Last-resort net - every step above already catches its own known failure modes, but this
  // guarantees an unforeseen bug in the script itself still can't fail a deploy over an SEO
  // enhancement.
  warn(`unexpected error: ${err.stack || err.message}`)
})
