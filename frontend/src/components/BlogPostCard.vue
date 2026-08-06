<script setup>
defineProps({
  post: {
    type: Object,
    required: true,
  },
})
</script>

<template>
  <RouterLink
    :to="`/blog/${post.slug}`"
    class="group flex flex-col overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-lg shadow-black/20 transition hover:shadow-xl hover:-translate-y-0.5"
  >
    <div class="aspect-[16/9] w-full overflow-hidden bg-page">
      <img
        v-if="post.cover_image"
        :src="post.cover_image"
        :alt="post.title"
        class="h-full w-full object-cover transition duration-300 group-hover:scale-105"
      />
      <div v-else class="flex h-full items-center justify-center text-foreground-subtle">SilverLake Car Rentals</div>
    </div>

    <div class="flex flex-1 flex-col gap-2 p-5">
      <div class="flex items-center gap-2">
        <span
          v-if="post.category_display"
          class="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-foreground-secondary"
        >
          {{ post.category_display }}
        </span>
        <p class="text-xs font-semibold uppercase tracking-widest text-accent">
          {{
            post.published_at
              ? new Date(post.published_at).toLocaleDateString(undefined, {
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                })
              : ''
          }}
        </p>
      </div>
      <h3 class="font-[Georgia] text-lg font-bold text-foreground">{{ post.title }}</h3>
      <p class="line-clamp-3 text-sm text-foreground-muted">{{ post.excerpt }}</p>
      <span class="mt-auto pt-3 text-sm font-semibold text-accent group-hover:text-accent-strong"> Read more &rarr; </span>
    </div>
  </RouterLink>
</template>
