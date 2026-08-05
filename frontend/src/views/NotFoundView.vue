<template>
  <div class="flex min-h-screen flex-col items-center justify-center bg-page px-4 text-center">
    <p class="font-[Georgia] text-8xl font-bold text-accent sm:text-9xl">404</p>
    <h1 class="mt-4 font-[Georgia] text-2xl font-bold text-foreground sm:text-3xl">Page not found</h1>
    <p class="mt-3 max-w-md text-foreground-muted">The page you're looking for doesn't exist or may have been moved.</p>
    <div class="mt-8 flex flex-wrap justify-center gap-4">
      <RouterLink
        to="/"
        class="rounded-lg bg-accent-bg px-6 py-3 font-semibold text-on-accent transition hover:bg-accent-bg-hover"
      >
        Back to Home
      </RouterLink>
      <RouterLink
        to="/fleet"
        class="rounded-lg border border-border px-6 py-3 font-semibold text-foreground-secondary transition hover:border-accent-border hover:text-accent"
      >
        Browse Fleet
      </RouterLink>
    </div>
  </div>
</template>
