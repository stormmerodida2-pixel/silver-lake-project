<script setup>
import { useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

function stop() {
  const returnPath = auth.stopImpersonation()
  router.push(returnPath || '/admin')
}
</script>

<template>
  <div
    v-if="auth.impersonating"
    class="flex flex-wrap items-center justify-center gap-2 bg-gold-500 px-4 py-2 text-center text-sm font-semibold text-navy-950"
  >
    <span>
      Impersonating {{ auth.user?.first_name || auth.user?.email }}
      <span class="font-normal">({{ auth.user?.email }})</span>
      <span v-if="auth.user?.is_read_only_session" class="font-normal">- read-only, view only</span>
    </span>
    <button
      class="rounded-md bg-navy-950 px-3 py-1 text-xs font-bold text-gold-400 transition hover:bg-navy-800"
      @click="stop"
    >
      Stop Impersonating
    </button>
  </div>
</template>
