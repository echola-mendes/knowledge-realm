<script setup lang="ts">
defineProps<{ name: string }>();
</script>

<template>
  <svg class="ico" viewBox="0 0 24 24" aria-hidden="true">
    <template v-if="name === 'book'">
      <path d="M4 5.2c1.4-1 3.2-1.4 5.2-.6 1 .4 1.8 1 2.8 1.2v13.4c-1.1-.3-2.1-.9-3.2-1.3-1.8-.7-3.5-.3-4.8.6V5.2Z" />
      <path d="M20 5.2c-1.4-1-3.2-1.4-5.2-.6-1 .4-1.8 1-2.8 1.2v13.4c1.1-.3 2.1-.9 3.2-1.3 1.8-.7 3.5-.3 4.8.6V5.2Z" />
    </template>
    <template v-else-if="name === 'home'">
      <path d="m4 11 8-7.2L20 11" />
      <path d="M6.2 10.2V20h4.2v-5.2h3.2V20h4.2V10.2" />
    </template>
    <template v-else-if="name === 'doc'">
      <path d="M7.2 3.5h6.4L18.8 8.8V20a1 1 0 0 1-1 1H7.2a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1Z" />
      <path d="M13.6 3.5v5.3h5.2" />
      <path d="M9 13.2h6.2M9 16.8h4.2" />
    </template>
    <template v-else-if="name === 'search'">
      <circle cx="11" cy="11" r="6.2" />
      <path d="m15.8 15.8 4.4 4.4" />
    </template>
    <template v-else-if="name === 'chat'">
      <path d="M7.4 18.2 4.2 20.4V7.6A2.6 2.6 0 0 1 6.8 5h10.4A2.6 2.6 0 0 1 19.8 7.6v6.4a2.6 2.6 0 0 1-2.6 2.6H9.2Z" />
    </template>
    <template v-else-if="name === 'gear'">
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2.6v2.2M12 19.2v2.2M4.1 4.1l1.6 1.6M18.3 18.3l1.6 1.6M2.6 12h2.2M19.2 12h2.2M4.1 19.9l1.6-1.6M18.3 5.7l1.6-1.6" />
      <circle cx="12" cy="12" r="8.2" />
    </template>
    <template v-else-if="name === 'db'">
      <ellipse cx="12" cy="6.2" rx="7.2" ry="2.5" />
      <path d="M4.8 6.2v4.6c0 1.4 3.2 2.5 7.2 2.5s7.2-1.1 7.2-2.5V6.2" />
      <path d="M4.8 10.8v4.8c0 1.4 3.2 2.5 7.2 2.5s7.2-1.1 7.2-2.5v-4.8" />
    </template>
    <template v-else-if="name === 'chevron'">
      <path d="m7 9.5 5 5 5-5" />
    </template>
  </svg>
</template>
