<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  data: { type: Array, required: true }, // [{ month: 'YYYY-MM', revenue: number }, ...]
})

// A darkened step of the brand's own gold (c9a227) - the UI's gold-500 reads too light for a
// dark-surface chart mark (fails the OKLCH lightness band for dark categorical/sequential data;
// see the dataviz skill's validate_palette.js), so charts use this chart-only variant instead of
// introducing an unrelated hue.
const GOLD = '#96751e'

const WIDTH = 720
const HEIGHT = 220
const PAD_LEFT = 56
const PAD_RIGHT = 16
const PAD_TOP = 16
const PAD_BOTTOM = 28
const plotWidth = WIDTH - PAD_LEFT - PAD_RIGHT
const plotHeight = HEIGHT - PAD_TOP - PAD_BOTTOM

const maxValue = computed(() => {
  const max = Math.max(1, ...props.data.map((d) => d.revenue))
  // Round the axis ceiling up to a clean step so gridline labels are round numbers (KES 5K,
  // 10K...), never a jagged max like "KES 47,382".
  const magnitude = Math.pow(10, Math.floor(Math.log10(max)))
  const step = magnitude / 2 || 1
  return Math.ceil(max / step) * step
})

function xFor(index) {
  if (props.data.length <= 1) return PAD_LEFT
  return PAD_LEFT + (index / (props.data.length - 1)) * plotWidth
}
function yFor(value) {
  return PAD_TOP + plotHeight - (value / maxValue.value) * plotHeight
}

const gridLines = computed(() => {
  const steps = 4
  return Array.from({ length: steps + 1 }, (_, i) => {
    const value = (maxValue.value / steps) * i
    return { value, y: yFor(value) }
  })
})

const linePath = computed(() =>
  props.data.map((d, i) => `${i === 0 ? 'M' : 'L'} ${xFor(i)} ${yFor(d.revenue)}`).join(' '),
)
const areaPath = computed(() => {
  if (!props.data.length) return ''
  return `${linePath.value} L ${xFor(props.data.length - 1)} ${PAD_TOP + plotHeight} L ${xFor(0)} ${PAD_TOP + plotHeight} Z`
})

function monthLabel(monthStr) {
  const [year, month] = monthStr.split('-').map(Number)
  return new Date(year, month - 1, 1).toLocaleDateString('en-US', { month: 'short' })
}

function fmtKES(value) {
  if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`
  if (value >= 1000) return `${Math.round(value / 1000)}K`
  return String(Math.round(value))
}

// ── Hover crosshair + tooltip (interaction.md: "the crosshair finds the X") ──────────────────
const svgRef = ref(null)
const hoverIndex = ref(null)

function onMouseMove(event) {
  if (!svgRef.value || !props.data.length) return
  const rect = svgRef.value.getBoundingClientRect()
  const relativeX = ((event.clientX - rect.left) / rect.width) * WIDTH
  let closest = 0
  let closestDist = Infinity
  props.data.forEach((_, i) => {
    const dist = Math.abs(xFor(i) - relativeX)
    if (dist < closestDist) {
      closestDist = dist
      closest = i
    }
  })
  hoverIndex.value = closest
}
function onMouseLeave() {
  hoverIndex.value = null
}

const tooltipStyle = computed(() => {
  if (hoverIndex.value === null) return {}
  return { left: `${(xFor(hoverIndex.value) / WIDTH) * 100}%` }
})
</script>

<template>
  <div class="relative">
    <svg
      ref="svgRef" :viewBox="`0 0 ${WIDTH} ${HEIGHT}`" class="w-full" style="height: 220px" preserveAspectRatio="none"
      @mousemove="onMouseMove" @mouseleave="onMouseLeave"
    >
      <g v-for="line in gridLines" :key="line.value">
        <line :x1="PAD_LEFT" :x2="WIDTH - PAD_RIGHT" :y1="line.y" :y2="line.y" stroke="#16305c" stroke-width="1" />
        <text :x="PAD_LEFT - 8" :y="line.y + 4" text-anchor="end" font-size="11" fill="#64748b" style="font-variant-numeric: tabular-nums">
          {{ fmtKES(line.value) }}
        </text>
      </g>

      <path :d="areaPath" :fill="GOLD" fill-opacity="0.1" stroke="none" />
      <path :d="linePath" fill="none" :stroke="GOLD" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />

      <text v-for="(d, i) in data" :key="d.month" :x="xFor(i)" :y="HEIGHT - 8" text-anchor="middle" font-size="11" fill="#64748b">
        {{ monthLabel(d.month) }}
      </text>

      <g v-if="hoverIndex !== null">
        <line :x1="xFor(hoverIndex)" :x2="xFor(hoverIndex)" :y1="PAD_TOP" :y2="PAD_TOP + plotHeight" stroke="#3b4a6b" stroke-width="1" />
        <circle :cx="xFor(hoverIndex)" :cy="yFor(data[hoverIndex].revenue)" r="5" :fill="GOLD" stroke="#0a1730" stroke-width="2" />
      </g>
    </svg>

    <div
      v-if="hoverIndex !== null"
      class="pointer-events-none absolute top-2 -translate-x-1/2 rounded-lg border border-navy-700 bg-navy-950 px-3 py-2 text-xs shadow-lg"
      :style="tooltipStyle"
    >
      <p class="font-semibold text-white">{{ monthLabel(data[hoverIndex].month) }}</p>
      <p class="mt-0.5 font-bold text-gold-400">KES {{ Number(data[hoverIndex].revenue).toLocaleString() }}</p>
    </div>
  </div>
</template>
