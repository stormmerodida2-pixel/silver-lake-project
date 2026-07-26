const DEFAULT_TITLE = 'SilverLake Car Rentals'
const DEFAULT_DESCRIPTION =
  'SilverLake Car Rentals - premium car hire in Kisumu with drivers or self-drive. Prado, Voxy, Axio and vans available. Book instantly via WhatsApp or M-Pesa.'
const DEFAULT_IMAGE = 'https://silverlakecarentals.com/og-image.jpg'

function setMetaTag(attr, key, content) {
  if (!content) return
  let tag = document.head.querySelector(`meta[${attr}="${key}"]`)
  if (!tag) {
    tag = document.createElement('meta')
    tag.setAttribute(attr, key)
    document.head.appendChild(tag)
  }
  tag.setAttribute('content', content)
}

function setCanonical(url) {
  if (!url) return
  let link = document.head.querySelector('link[rel="canonical"]')
  if (!link) {
    link = document.createElement('link')
    link.setAttribute('rel', 'canonical')
    document.head.appendChild(link)
  }
  link.setAttribute('href', url)
}

/**
 * Updates document.title plus the description/canonical/Open Graph/Twitter meta tags - falls
 * back to the site-wide defaults for anything not passed, so every route (not just blog posts)
 * ends up with a sensible title/description instead of stale values from whichever page was
 * visited previously. `url` drives both the canonical link and og:url, so a page shared via its
 * client-side-navigated URL (not the first hard load) still points back at itself rather than
 * silently declaring the homepage canonical or the Open Graph scrape URL stale.
 */
export function setPageMeta({ title, description, image, url, type = 'website' } = {}) {
  const resolvedTitle = title || DEFAULT_TITLE
  const resolvedDescription = description || DEFAULT_DESCRIPTION
  document.title = resolvedTitle
  setMetaTag('name', 'description', resolvedDescription)
  setMetaTag('property', 'og:title', resolvedTitle)
  setMetaTag('property', 'og:description', resolvedDescription)
  setMetaTag('property', 'og:type', type)
  setMetaTag('property', 'og:image', image || DEFAULT_IMAGE)
  setMetaTag('name', 'twitter:title', resolvedTitle)
  setMetaTag('name', 'twitter:description', resolvedDescription)
  setMetaTag('name', 'twitter:image', image || DEFAULT_IMAGE)
  if (url) {
    setCanonical(url)
    setMetaTag('property', 'og:url', url)
  }
}
