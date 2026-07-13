const DEFAULT_TITLE = 'SilverLake Car Rentals'
const DEFAULT_DESCRIPTION =
  'SilverLake Car Rentals - premium car hire in Kisumu with drivers or self-drive. Prado, Voxy, Axio and vans available. Book instantly via WhatsApp or M-Pesa.'

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

/**
 * Updates document.title plus the description/Open Graph meta tags - falls back to the
 * site-wide defaults for anything not passed, so every route (not just blog posts) ends up
 * with a sensible title/description instead of stale values from whichever page was visited
 * previously.
 */
export function setPageMeta({ title, description, image, type = 'website' } = {}) {
  document.title = title || DEFAULT_TITLE
  setMetaTag('name', 'description', description || DEFAULT_DESCRIPTION)
  setMetaTag('property', 'og:title', title || DEFAULT_TITLE)
  setMetaTag('property', 'og:description', description || DEFAULT_DESCRIPTION)
  setMetaTag('property', 'og:type', type)
  setMetaTag('property', 'og:image', image || '')
}
