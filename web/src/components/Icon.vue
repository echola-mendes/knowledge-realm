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
    <template v-else-if="name === 'bug'">
      <circle cx="12" cy="14" r="5.2" />
      <path d="M12 8.8V5.5M8.2 6.2 10 8.2M15.8 6.2 14 8.2M4.8 12.2h2.4M16.8 12.2h2.4M5.5 17.5l2.2-1M18.5 17.5l-2.2-1" />
    </template>
    <template v-else-if="name === 'user'">
      <circle cx="12" cy="8.2" r="3.2" />
      <path d="M5.2 19.2c.8-3.4 3.4-5.2 6.8-5.2s6 1.8 6.8 5.2" />
    </template>
    <template v-else-if="name === 'lock'">
      <rect x="6.2" y="10.5" width="11.6" height="9" rx="1.6" />
      <path d="M8.4 10.5V8.2a3.6 3.6 0 0 1 7.2 0v2.3" />
    </template>
    <template v-else-if="name === 'eye'">
      <path d="M2.8 12s3.2-6.2 9.2-6.2S21.2 12 21.2 12s-3.2 6.2-9.2 6.2S2.8 12 2.8 12Z" />
      <circle cx="12" cy="12" r="2.6" />
    </template>
    <template v-else-if="name === 'eyeOff'">
      <path d="m4 4 16 16" />
      <path d="M9.1 9.2A3 3 0 0 0 12 15a3 3 0 0 0 2.7-1.6" />
      <path d="M6.2 6.8C4.2 8.2 2.8 12 2.8 12s3.2 6.2 9.2 6.2c1.7 0 3.2-.4 4.5-1" />
      <path d="M10.4 6C10.9 5.9 11.5 5.8 12 5.8c6 0 9.2 6.2 9.2 6.2a16 16 0 0 1-2.2 2.8" />
    </template>
    <template v-else-if="name === 'chevron'">
      <path d="m7 9.5 5 5 5-5" />
    </template>
  </svg>
</template>
