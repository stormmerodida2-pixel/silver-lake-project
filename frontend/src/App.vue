<script setup>
import NavBar from './components/NavBar.vue'
import Footer from './components/Footer.vue'
import WhatsAppButton from './components/WhatsAppButton.vue'
</script>

<template>
  <div class="flex min-h-screen flex-col bg-navy-950">
    <NavBar />
    <main class="flex-1">
      <RouterView />
    </main>
    <Footer />
    <WhatsAppButton />
  </div>
</template>
