<script setup>
import { computed } from 'vue'

const props = defineProps({
  // Always the full number the backend/M-Pesa's STK Push API expects: "254XXXXXXXXX", no "+" -
  // Safaricom's Daraja API rejects a leading "+", so that must never reach what gets submitted.
  // This component only ever DISPLAYS a fixed "+254" prefix; modelValue itself never has one.
  modelValue: { type: String, default: '' },
  required: { type: Boolean, default: false },
  // Admin forms are dark-themed, public-facing ones are light - everything else about sizing is
  // kept consistent across call sites rather than trying to match each one's exact prior look.
  dark: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

// Tolerates whatever shape existing data might already be in (a stray "+", a leading "0" from
// local dialing convention, or already-bare digits) so editing an existing phone number doesn't
// show a garbled prefix - only ever emits the normalized 254-prefixed form.
const localDigits = computed({
  get() {
    const digits = (props.modelValue || '').replace(/\D/g, '')
    if (digits.startsWith('254')) return digits.slice(3)
    if (digits.startsWith('0')) return digits.slice(1)
    return digits
  },
  set(value) {
    const digits = value.replace(/\D/g, '').slice(0, 9)
    emit('update:modelValue', digits ? `254${digits}` : '')
  },
})
</script>

<template>
  <div
    class="flex overflow-hidden rounded-md border focus-within:border-brand-blue-500"
    :class="dark ? 'border-navy-700 bg-navy-800' : 'border-slate-300 bg-white'"
  >
    <span
      class="flex select-none items-center px-3 text-sm font-medium"
      :class="dark ? 'bg-navy-700 text-slate-300' : 'bg-slate-100 text-slate-500'"
    >
      +254
    </span>
    <input
      v-model="localDigits"
      type="tel"
      inputmode="numeric"
      placeholder="712345678"
      :required="required"
      pattern="[17][0-9]{8}"
      minlength="9"
      maxlength="9"
      title="A real Kenyan mobile number: 9 digits, starting with 7 or 1 (e.g. 712345678)"
      class="w-full min-w-0 border-0 bg-transparent px-3 py-2.5 focus:outline-none focus:ring-0"
      :class="dark ? 'text-white placeholder-slate-500' : 'text-navy-900 placeholder-slate-400'"
    />
  </div>
</template>
