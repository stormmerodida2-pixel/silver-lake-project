<script setup>
import SilverLakeLogo from './SilverLakeLogo.vue'

const year = new Date().getFullYear()
</script>

<template>
  <footer class="border-t border-navy-800 bg-navy-900">
    <div class="mx-auto grid max-w-6xl gap-8 px-4 py-10 sm:px-6 md:grid-cols-4">
      <div>
        <div class="flex items-center gap-2">
          <SilverLakeLogo :size="28" />
          <h3 class="font-[Georgia] text-lg font-bold text-white">SILVERLAKE CAR RENTALS</h3>
        </div>
        <p class="mt-2 text-sm text-slate-400">
          Rooted in Kisumu, driven across Kenya. Safe journeys, happy clients, every time.
        </p>
        <div class="mt-3 flex flex-wrap gap-4 text-sm">
          <RouterLink to="/drivers" class="text-slate-300 hover:text-gold-400">Meet Our Drivers</RouterLink>
          <RouterLink to="/reviews" class="text-slate-300 hover:text-gold-400">Leave a Review</RouterLink>
          <RouterLink to="/become-a-driver" class="text-slate-300 hover:text-gold-400">Become a Driver</RouterLink>
          <RouterLink to="/contact" class="text-slate-300 hover:text-gold-400">Contact Us</RouterLink>
        </div>
      </div>

      <div>
        <h4 class="text-sm font-semibold uppercase tracking-wide text-gold-400">Contact</h4>
        <ul class="mt-2 space-y-1 text-sm text-slate-300">
          <li>0790 111 000</li>
          <li>0700 000 000</li>
          <li>info@silverlakecarrentals.co.ke</li>
          <li>Kisumu, Kenya</li>
        </ul>
      </div>

      <div>
        <h4 class="text-sm font-semibold uppercase tracking-wide text-gold-400">Payments</h4>
        <ul class="mt-2 space-y-1 text-sm text-slate-300">
          <li>M-Pesa Paybill: 400400 (Acc: SILVERLAKE)</li>
          <li>M-Pesa Till: 1234567</li>
          <li>Bank: Co-operative Bank of Kenya</li>
        </ul>
      </div>

      <div>
        <h4 class="text-sm font-semibold uppercase tracking-wide text-gold-400">Legal</h4>
        <ul class="mt-2 space-y-1 text-sm text-slate-300">
          <li><RouterLink to="/terms" class="hover:text-gold-400">Terms of Service</RouterLink></li>
          <li><RouterLink to="/privacy" class="hover:text-gold-400">Privacy Policy</RouterLink></li>
          <li><RouterLink to="/refund-policy" class="hover:text-gold-400">Refund &amp; Cancellation</RouterLink></li>
        </ul>
      </div>
    </div>

    <div class="border-t border-navy-800 py-4 text-center text-xs text-slate-500">
      &copy; {{ year }} SilverLake Car Rentals. All rights reserved.
    </div>
  </footer>
</template>
