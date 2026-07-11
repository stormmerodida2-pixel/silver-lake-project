<template>
  <div class="flex min-h-screen flex-col items-center justify-center bg-navy-950 px-4 text-center">
    <p class="font-[Georgia] text-8xl font-bold text-gold-400 sm:text-9xl">404</p>
    <h1 class="mt-4 font-[Georgia] text-2xl font-bold text-white sm:text-3xl">Page not found</h1>
    <p class="mt-3 max-w-md text-slate-400">
      The page you're looking for doesn't exist or may have been moved.
    </p>
    <div class="mt-8 flex flex-wrap justify-center gap-4">
      <RouterLink
        to="/"
        class="rounded-lg bg-gold-500 px-6 py-3 font-semibold text-navy-950 transition hover:bg-gold-400"
      >
        Back to Home
      </RouterLink>
      <RouterLink
        to="/fleet"
        class="rounded-lg border border-navy-700 px-6 py-3 font-semibold text-slate-300 transition hover:border-gold-400 hover:text-gold-400"
      >
        Browse Fleet
      </RouterLink>
    </div>
  </div>
</template>
