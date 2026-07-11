<template>
  <div class="bg-white">
    <section class="bg-navy-950 py-16">
      <div class="mx-auto max-w-3xl px-4 text-center sm:px-6">
        <p class="text-sm font-semibold uppercase tracking-widest text-gold-400">Legal</p>
        <h1 class="mt-3 font-[Georgia] text-4xl font-bold text-white">Refund &amp; Cancellation Policy</h1>
        <p class="mt-3 text-sm text-slate-400">Last updated: 4 July 2026</p>
      </div>
    </section>

    <section class="mx-auto max-w-3xl px-4 py-16 sm:px-6">
      <div class="space-y-10 text-slate-700">
        <p class="leading-relaxed">
          This policy explains how deposits, cancellations, and refunds work for SilverLake Car Rentals
          bookings. It applies alongside our
          <RouterLink to="/terms" class="font-semibold text-brand-blue-600 hover:text-brand-blue-500">Terms of Service</RouterLink>.
        </p>

        <div>
          <h2 class="font-[Georgia] text-xl font-bold text-navy-900">1. Deposit to Confirm</h2>
          <p class="mt-3 leading-relaxed">
            A booking is held as "pending" until a deposit of at least 30% of the total cost is paid; the
            booking is only confirmed once that deposit clears. The remaining balance may be paid any time
            before pickup, or in full at pickup.
          </p>
        </div>

        <div>
          <h2 class="font-[Georgia] text-xl font-bold text-navy-900">2. Cancelling a With-Driver Booking</h2>
          <p class="mt-3 leading-relaxed">
            For with-driver bookings, how much of your deposit and service fee is refunded depends on who
            cancels and when:
          </p>
          <div class="mt-4 overflow-x-auto rounded-xl border border-slate-200">
            <table class="w-full text-left text-sm">
              <thead class="bg-slate-50 text-navy-900">
                <tr>
                  <th class="px-4 py-3 font-semibold">Scenario</th>
                  <th class="px-4 py-3 font-semibold">Deposit Refund</th>
                  <th class="px-4 py-3 font-semibold">Service Fee</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-200">
                <tr>
                  <td class="px-4 py-3">Driver doesn't show up</td>
                  <td class="px-4 py-3 font-semibold text-brand-blue-600">100%</td>
                  <td class="px-4 py-3 text-slate-500">Not refunded</td>
                </tr>
                <tr>
                  <td class="px-4 py-3">Driver cancels/can't make it</td>
                  <td class="px-4 py-3 font-semibold text-brand-blue-600">100%</td>
                  <td class="px-4 py-3 text-slate-500">Not refunded</td>
                </tr>
                <tr>
                  <td class="px-4 py-3">Client cancels after driver arrives</td>
                  <td class="px-4 py-3 font-semibold text-brand-blue-600">50%</td>
                  <td class="px-4 py-3 text-slate-500">Not refunded</td>
                </tr>
                <tr>
                  <td class="px-4 py-3">Client cancels before driver accepts (optional)</td>
                  <td class="px-4 py-3 font-semibold text-brand-blue-600">100%</td>
                  <td class="px-4 py-3 text-slate-500">Refunded or retained (SilverLake's choice)</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="mt-3 leading-relaxed text-sm text-slate-500">
            "Service fee" refers to the platform/booking fee charged separately from the vehicle deposit.
          </p>
        </div>

        <div>
          <h2 class="font-[Georgia] text-xl font-bold text-navy-900">3. Cancelling a Self-Drive Booking</h2>
          <p class="mt-3 leading-relaxed">If you cancel a confirmed self-drive booking through your account:</p>
          <ul class="mt-3 list-disc space-y-2 pl-5 leading-relaxed">
            <li><strong>More than 48 hours before pickup:</strong> full refund of any amount paid.</li>
            <li><strong>24-48 hours before pickup:</strong> 50% of the deposit is refunded; the remainder covers vehicle-holding costs.</li>
            <li><strong>Less than 24 hours before pickup, or a no-show:</strong> the deposit is non-refundable.</li>
          </ul>
          <p class="mt-3 leading-relaxed text-sm text-slate-500">
            These windows are measured from your scheduled pickup date/time to the moment you cancel.
          </p>
        </div>

        <div>
          <h2 class="font-[Georgia] text-xl font-bold text-navy-900">4. Cancellations by SilverLake</h2>
          <p class="mt-3 leading-relaxed">
            If we cancel your booking - for example, because a vehicle becomes unavailable due to a mechanical
            issue, lapsed insurance, or an inspection failure - you will receive a full refund of everything
            paid, or the option to rebook a comparable vehicle at no extra cost.
          </p>
        </div>

        <div>
          <h2 class="font-[Georgia] text-xl font-bold text-navy-900">5. How Refunds Are Processed</h2>
          <p class="mt-3 leading-relaxed">
            Approved refunds are sent back to the M-Pesa number used for payment (or the original payment
            method, once card payments are available) within 5-7 business days. Contact us if a refund
            hasn't arrived after that window.
          </p>
        </div>

        <div>
          <h2 class="font-[Georgia] text-xl font-bold text-navy-900">6. Mid-Trip Issues</h2>
          <p class="mt-3 leading-relaxed">
            If a vehicle breaks down or a driver is unable to continue a with-driver trip due to a fault on
            our side, we will arrange a replacement vehicle/driver where possible, or refund the unused
            portion of your trip on a pro-rata basis.
          </p>
        </div>

        <div>
          <h2 class="font-[Georgia] text-xl font-bold text-navy-900">7. Disputes</h2>
          <p class="mt-3 leading-relaxed">
            If you believe a cancellation or refund was handled incorrectly, contact us and we'll review it
            manually - most refund questions are resolved within a few business days.
          </p>
        </div>

        <div>
          <h2 class="font-[Georgia] text-xl font-bold text-navy-900">8. Contact Us</h2>
          <p class="mt-3 leading-relaxed">
            For cancellations or refund questions, email
            <a href="mailto:info@silverlakecarrentals.co.ke" class="font-semibold text-brand-blue-600 hover:text-brand-blue-500">
              info@silverlakecarrentals.co.ke
            </a>
            or call 0790 111 000.
          </p>
        </div>
      </div>
    </section>
  </div>
</template>
