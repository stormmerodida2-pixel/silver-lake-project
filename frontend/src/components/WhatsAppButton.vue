<script setup>
const whatsappNumber = import.meta.env.VITE_WHATSAPP_NUMBER
const message = encodeURIComponent(
  "Hi SilverLake! I'd like to inquire about hiring a vehicle."
)
const href = `https://wa.me/${whatsappNumber}?text=${message}`
</script>

<template>
  <a
    :href="href"
    target="_blank"
    rel="noopener"
    aria-label="Chat with us on WhatsApp"
    class="fixed bottom-5 right-5 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-[#25D366] text-white shadow-lg shadow-black/30 transition hover:scale-105"
  >
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" class="h-8 w-8" fill="currentColor">
      <path
        d="M16.004 3C9.376 3 4 8.373 4 15c0 2.34.652 4.53 1.786 6.4L4 29l7.77-1.75A11.94 11.94 0 0 0 16.004 27C22.63 27 28 21.627 28 15S22.63 3 16.004 3Zm0 21.6a9.55 9.55 0 0 1-4.87-1.33l-.35-.2-4.61 1.04 1.02-4.5-.23-.37A9.56 9.56 0 1 1 25.56 15c0 5.29-4.3 9.6-9.556 9.6Zm5.24-7.17c-.29-.14-1.71-.84-1.97-.94-.26-.1-.46-.14-.65.14-.19.28-.75.94-.92 1.13-.17.19-.34.22-.63.07-.29-.14-1.21-.45-2.3-1.42-.85-.76-1.42-1.7-1.59-1.98-.17-.28-.02-.44.13-.58.13-.13.29-.34.43-.51.14-.17.19-.28.29-.47.1-.19.05-.36-.02-.5-.07-.14-.65-1.57-.9-2.15-.24-.57-.48-.5-.65-.5h-.56c-.19 0-.5.07-.76.36-.26.28-1 1-1 2.42 0 1.43 1.03 2.81 1.17 3 .14.19 2.03 3.1 4.91 4.35.69.3 1.22.48 1.64.61.69.22 1.31.19 1.81.11.55-.08 1.71-.7 1.95-1.37.24-.68.24-1.26.17-1.37-.07-.12-.26-.19-.55-.33Z"
      />
    </svg>
  </a>
</template>
