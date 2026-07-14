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
    class="group flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg shadow-slate-200/60 transition hover:shadow-xl hover:-translate-y-0.5"
  >
    <div class="aspect-[16/9] w-full overflow-hidden bg-slate-100">
      <img
        v-if="post.cover_image"
        :src="post.cover_image"
        :alt="post.title"
        class="h-full w-full object-cover transition duration-300 group-hover:scale-105"
      />
      <div v-else class="flex h-full items-center justify-center text-slate-400">SilverLake Car Rentals</div>
    </div>

    <div class="flex flex-1 flex-col gap-2 p-5">
      <div class="flex items-center gap-2">
        <span v-if="post.category_display" class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-slate-600">
          {{ post.category_display }}
        </span>
        <p class="text-xs font-semibold uppercase tracking-widest text-brand-blue-600">
          {{ post.published_at ? new Date(post.published_at).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' }) : '' }}
        </p>
      </div>
      <h3 class="font-[Georgia] text-lg font-bold text-navy-900">{{ post.title }}</h3>
      <p class="line-clamp-3 text-sm text-slate-600">{{ post.excerpt }}</p>
      <span class="mt-auto pt-3 text-sm font-semibold text-gold-600 group-hover:text-gold-500">
        Read more &rarr;
      </span>
    </div>
  </RouterLink>
</template>
