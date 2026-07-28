<script setup>
import { onMounted } from 'vue'
import { setStructuredData } from '../utils/seo'

// Every answer is traced to a real source (RefundPolicyView.vue's own policy text,
// Booking.clean()'s self-drive document requirement, BookingView.vue's live bank-transfer
// details) rather than invented - this is public-facing content a customer might actually act
// on (e.g. where to send a bank transfer), so nothing here should be a guess.
const faqs = [
  {
    question: 'How much deposit do I need to pay to book a car in Kisumu with SilverLake?',
    answer:
      'A deposit of at least 30% of the total rental cost is required to confirm your booking. The booking stays "pending" until the deposit clears; the remaining balance can be paid any time before pickup, or in full at pickup.',
  },
  {
    question: 'What payment methods does SilverLake Car Rentals accept?',
    answer:
      'Bookings can be paid via M-Pesa or bank transfer to Co-operative Bank of Kenya (Paybill 400200, Account No. 01101465587001) - use your name and booking number as the reference so payment can be matched. Refunds are sent back to the M-Pesa number used for payment within 5-7 business days.',
  },
  {
    question: 'Can I cancel a self-drive booking and get a refund?',
    answer:
      'Yes. More than 48 hours before pickup: full refund. 24-48 hours before pickup: 50% of the deposit refunded. Less than 24 hours before pickup, or a no-show: the deposit is non-refundable.',
  },
  {
    question: 'What happens if my with-driver booking is cancelled?',
    answer:
      "Depends on who cancels and when. If the driver doesn't show up or cancels, you get a 100% deposit refund. If you cancel after the driver has already arrived, you get a 50% deposit refund; the separate service fee isn't refunded in that case.",
  },
  {
    question: 'What documents do I need for a self-drive rental in Kisumu?',
    answer:
      'A valid driving license and a national ID or passport, uploaded at the time of booking, are required before a self-drive reservation can be confirmed.',
  },
  {
    question: 'Does SilverLake Car Rentals operate outside Kisumu?',
    answer: 'Yes - based in Kisumu, serving destinations across Kenya.',
  },
  {
    question: 'What types of vehicles are available to hire?',
    answer:
      'SUVs such as the Toyota Prado, family vehicles such as the Toyota Voxy and Axio, and vans - available with a professional driver, for self-drive, or both depending on the vehicle.',
  },
  {
    question: 'How long does it take to get a refund?',
    answer: 'Approved refunds are sent back within 5-7 business days.',
  },
  {
    question: 'What happens if SilverLake has to cancel my booking?',
    answer: 'A full refund of everything paid, or the option to rebook a comparable vehicle at no extra cost.',
  },
  {
    question: 'How do I contact SilverLake Car Rentals?',
    answer: 'Email info@silverlakecarrentals.co.ke or call 0798 184 193.',
  },
]

onMounted(() => {
  setStructuredData('ld-dynamic-faq', {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: faqs.map((f) => ({
      '@type': 'Question',
      name: f.question,
      acceptedAnswer: { '@type': 'Answer', text: f.answer },
    })),
  })
})
</script>

<template>
  <div class="bg-white">
    <section class="bg-navy-950 py-16">
      <div class="mx-auto max-w-3xl px-4 text-center sm:px-6">
        <p class="text-sm font-semibold uppercase tracking-widest text-gold-400">Help</p>
        <h1 class="mt-3 font-[Georgia] text-4xl font-bold text-white">Frequently Asked Questions</h1>
        <p class="mt-3 text-sm text-slate-400">
          Answers to common questions about booking, payment, cancellations and documents.
        </p>
      </div>
    </section>

    <section class="mx-auto max-w-3xl px-4 py-16 sm:px-6">
      <div class="space-y-10 text-slate-700">
        <div v-for="faq in faqs" :key="faq.question">
          <h2 class="font-[Georgia] text-xl font-bold text-navy-900">{{ faq.question }}</h2>
          <p class="mt-3 leading-relaxed">{{ faq.answer }}</p>
        </div>
      </div>

      <p class="mt-12 border-t border-slate-200 pt-8 text-sm text-slate-500">
        Have a question we haven't covered? Email
        <a href="mailto:info@silverlakecarrentals.co.ke" class="font-semibold text-brand-blue-600 hover:text-brand-blue-500"
          >info@silverlakecarrentals.co.ke</a
        >
        or call 0798 184 193.
      </p>
    </section>
  </div>
</template>
