// v-reveal: fades/slides an element in the moment it scrolls into view. Registered globally in
// main.js. Respects prefers-reduced-motion by doing nothing at all - the element just renders
// normally, no animation, no observer.
const prefersReducedMotion = () =>
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

export default {
  mounted(el) {
    if (prefersReducedMotion()) return

    el.style.opacity = '0'
    el.style.transform = 'translateY(20px)'
    el.style.transition = 'opacity 0.6s ease-out, transform 0.6s ease-out'

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return
        el.style.opacity = '1'
        el.style.transform = 'translateY(0)'
        observer.disconnect()
      },
      { threshold: 0.15, rootMargin: '0px 0px -40px 0px' },
    )
    observer.observe(el)
    el.__revealObserver = observer
  },
  unmounted(el) {
    el.__revealObserver?.disconnect()
  },
}
