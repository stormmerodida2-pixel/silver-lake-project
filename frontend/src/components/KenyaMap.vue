<script setup>
// A stylized, low-poly Kenya silhouette - not a precise cartographic trace, just enough of a
// read to anchor "we're rooted in Kisumu, we reach the rest of Kenya" without pretending to be
// a real photograph or a surveyed map. Marker coordinates are hand-placed approximations of
// each city's real relative position, not measured data.
defineProps({
  // 'origin' - just Kisumu, glowing, for the "Rooted in Kisumu" section.
  // 'routes' - Kisumu plus reachable destinations with fan-out lines, for the footer.
  mode: {
    type: String,
    default: 'origin',
    validator: (value) => ['origin', 'routes'].includes(value),
  },
})

const KISUMU = { x: 55, y: 128 }
const DESTINATIONS = [
  { name: 'Nairobi', x: 100, y: 166 },
  { name: 'Mombasa', x: 142, y: 197 },
  { name: 'Nakuru', x: 90, y: 129 },
  { name: 'Eldoret', x: 60, y: 88 },
  { name: 'Malindi', x: 156, y: 176 },
]

const KENYA_OUTLINE = 'M100,8 L130,20 L150,45 L165,70 L175,100 L170,130 L155,160 L165,185 L150,210 L120,225 L95,215 L80,190 L60,175 L45,150 L50,120 L40,95 L45,65 L65,35 L85,15 Z'
</script>

<template>
  <svg viewBox="0 0 200 240" class="h-full w-full" aria-hidden="true">
    <path :d="KENYA_OUTLINE" class="fill-navy-700/70 stroke-gold-400/70" stroke-width="2" />

    <template v-if="mode === 'routes'">
      <line
        v-for="dest in DESTINATIONS"
        :key="`line-${dest.name}`"
        :x1="KISUMU.x"
        :y1="KISUMU.y"
        :x2="dest.x"
        :y2="dest.y"
        class="stroke-gold-400/50"
        stroke-width="0.75"
        stroke-dasharray="3 3"
      />
      <g v-for="dest in DESTINATIONS" :key="dest.name">
        <circle :cx="dest.x" :cy="dest.y" r="3.5" class="fill-brand-blue-400" />
      </g>
    </template>

    <g>
      <circle :cx="KISUMU.x" :cy="KISUMU.y" r="9" class="fill-gold-400/20">
        <animate attributeName="r" values="9;13;9" dur="2.5s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.5;0;0.5" dur="2.5s" repeatCount="indefinite" />
      </circle>
      <path
        :transform="`translate(${KISUMU.x - 5}, ${KISUMU.y - 9}) scale(0.42)`"
        d="M12 21s-6.716-4.35-9.428-8.028C.86 10.42 1.02 7.36 3.343 5.6a5.5 5.5 0 0 1 7.657 1.02L12 7.8l1-1.18a5.5 5.5 0 0 1 7.657-1.02c2.323 1.76 2.483 4.82.77 7.372C18.716 16.65 12 21 12 21Z"
        class="fill-gold-400"
      />
    </g>
  </svg>
</template>
