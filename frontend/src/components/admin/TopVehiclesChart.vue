<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  data: { type: Array, required: true }, // [{ id, name, bookings, revenue }, ...]
})

// Same chart-only darkened gold as RevenueTrendChart.vue - see its comment for why gold-500
// itself isn't used directly on a dark chart surface.
const GOLD = '#96751e'

const BAR_HEIGHT = 22
const BAR_GAP = 14
const WIDTH = 720
const LABEL_WIDTH = 160
const PAD_RIGHT = 100
const plotWidth = WIDTH - LABEL_WIDTH - PAD_RIGHT

const maxRevenue = computed(() => Math.max(1, ...props.data.map((d) => d.revenue)))
const height = computed(() => props.data.length * (BAR_HEIGHT + BAR_GAP) + BAR_GAP)

function barWidth(revenue) {
  return (revenue / maxRevenue.value) * plotWidth
}
function rowY(i) {
  return BAR_GAP + i * (BAR_HEIGHT + BAR_GAP)
}
function truncate(name) {
  return name.length > 22 ? `${name.slice(0, 21)}…` : name
}

const hoverIndex = ref(null)
const tooltipStyle = computed(() => {
  if (hoverIndex.value === null) return {}
  const row = props.data[hoverIndex.value]
  return {
    left: `${((LABEL_WIDTH + barWidth(row.revenue) / 2) / WIDTH) * 100}%`,
    top: `${(rowY(hoverIndex.value) / height.value) * 100}%`,
  }
})
</script>

<template>
  <div class="relative">
    <svg :viewBox="`0 0 ${WIDTH} ${height}`" class="w-full">
      <g
        v-for="(row, i) in data"
        :key="row.id"
        tabindex="0"
        class="cursor-pointer focus:outline-none"
        @mouseenter="hoverIndex = i"
        @mouseleave="hoverIndex = null"
        @focus="hoverIndex = i"
        @blur="hoverIndex = null"
      >
        <text :x="LABEL_WIDTH - 10" :y="rowY(i) + BAR_HEIGHT / 2 + 4" text-anchor="end" font-size="12" fill="#cbd5e1">
          {{ truncate(row.name) }}
        </text>
        <rect
          :x="LABEL_WIDTH"
          :y="rowY(i)"
          :width="Math.max(barWidth(row.revenue), 3)"
          :height="BAR_HEIGHT"
          rx="4"
          :fill="GOLD"
          :fill-opacity="hoverIndex === i ? 1 : 0.85"
        />
        <text
          :x="LABEL_WIDTH + barWidth(row.revenue) + 8"
          :y="rowY(i) + BAR_HEIGHT / 2 + 4"
          font-size="11"
          fill="#94a3b8"
          style="font-variant-numeric: tabular-nums"
        >
          KES {{ Number(row.revenue).toLocaleString() }}
        </text>
      </g>
    </svg>

    <div
      v-if="hoverIndex !== null"
      class="pointer-events-none absolute -translate-x-1/2 -translate-y-full rounded-lg border border-navy-700 bg-navy-950 px-3 py-2 text-xs shadow-lg"
      :style="tooltipStyle"
    >
      <p class="font-semibold text-white">{{ data[hoverIndex].name }}</p>
      <p class="mt-0.5 font-bold text-gold-400">KES {{ Number(data[hoverIndex].revenue).toLocaleString() }}</p>
      <p class="text-slate-400">
        {{ data[hoverIndex].bookings }} booking{{ data[hoverIndex].bookings === 1 ? '' : 's' }}
      </p>
    </div>

    <p v-if="!data.length" class="py-6 text-center text-sm text-slate-500">No bookings in the last 12 months.</p>
  </div>
</template>
