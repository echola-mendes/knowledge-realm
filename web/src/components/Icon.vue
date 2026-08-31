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
    <template v-else-if="name === 'session'">
      <path d="M12 4.6c-4.1 0-7.4 2.6-7.4 5.9 0 1.9 1.1 3.5 2.8 4.6v3.4l3.1-1.7c.5.1 1 .1 1.5.1 4.1 0 7.4-2.6 7.4-5.9S16.1 4.6 12 4.6Z" />
      <circle cx="8.8" cy="10.5" r="0.7" fill="currentColor" stroke="none" />
      <circle cx="12" cy="10.5" r="0.7" fill="currentColor" stroke="none" />
      <circle cx="15.2" cy="10.5" r="0.7" fill="currentColor" stroke="none" />
    </template>
    <template v-else-if="name === 'paperclip'">
      <path d="m20.3 11.2-7.9 7.9a5 5 0 0 1-7.1-7.1l8.3-8.3a3.4 3.4 0 0 1 4.8 4.8l-8.3 8.3a1.8 1.8 0 0 1-2.5-2.5l7.6-7.6" />
    </template>
    <template v-else-if="name === 'image'">
      <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" />
      <circle cx="9" cy="9.8" r="1.6" />
      <path d="m5 18.5 4.8-5 3.2 3.2 2.8-2.8 3.7 3.7" />
    </template>
    <template v-else-if="name === 'tools'">
      <path d="M14.3 6.3a3.6 3.6 0 0 1 4.9-4.5l-2.8 2.8 1.5 1.5 2.8-2.8a3.6 3.6 0 0 1-4.5 4.9L7.6 16.8a2 2 0 1 1-2.8-2.8L13.2 5.4" />
      <path d="m4.5 19.5 1.5-1.5" />
    </template>
    <template v-else-if="name === 'report'">
      <path d="M7.2 4h9.6a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H7.2a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z" />
      <path d="M9 15.5 11.5 12l2 1.5 2.5-3.5" />
    </template>
    <template v-else-if="name === 'send'">
      <path d="m22 2-7 20-4-9-9-4 20-7z" fill="currentColor" stroke="none" />
    </template>
    <template v-else-if="name === 'upload'">
      <path d="M12 16V4.5" />
      <path d="m7.5 9 4.5-4.5L16.5 9" />
      <path d="M4.5 15.5v3a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-3" />
    </template>
    <template v-else-if="name === 'plus'">
     <path d="M12 5v14M5 12h14" />
   </template>
    <template v-else-if="name === 'minus'">
      <path d="M5 12h14" />
    </template>
    <template v-else-if="name === 'maximize'">
      <path d="M4.5 4.5h15v15h-15z" />
      <path d="M4.5 9.5h15M9.5 4.5v15" />
    </template>
    <template v-else-if="name === 'refresh'">
      <path d="M20 11A8 8 0 1 1 6.3 7.3" />
      <path d="M20 4v7h-7" />
    </template>
    <template v-else-if="name === 'fullscreen'">
      <path d="M4.5 9.5V4.5h5M19.5 9.5V4.5h-5M4.5 14.5v5h5M19.5 14.5v5h-5" />
    </template>
    <template v-else-if="name === 'chevron-left'">
      <path d="m14 7-5 5 5 5" />
    </template>
    <template v-else-if="name === 'edit'">
      <path d="M12 20h9M16.5 3.5a1.8 1.8 0 0 1 2.5 2.5L7 18l-4 1 1-4 12.5-12.5Z" />
    </template>
    <template v-else-if="name === 'share'">
      <path d="M16 8a2.2 2.2 0 1 0-2.2-2.2M8 14.5a2.2 2.2 0 1 0-2.2-2.2M16 20.8a2.2 2.2 0 1 0-2.2-2.2M9.8 13.3l4.4-2.6M9.8 10.7l4.4 2.6" />
    </template>
    <template v-else-if="name === 'star'">
      <path d="m12 3.8 2.2 4.5 4.9.7-3.5 3.4.8 4.9L12 14.8l-4.4 2.3.8-4.9-3.5-3.4 4.9-.7L12 3.8Z" />
    </template>
    <template v-else-if="name === 'more'">
      <circle cx="5.5" cy="12" r="1.6" fill="currentColor" stroke="none" />
      <circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none" />
      <circle cx="18.5" cy="12" r="1.6" fill="currentColor" stroke="none" />
    </template>
    <template v-else-if="name === 'panel-close'">
      <rect x="4" y="5" width="16" height="14" rx="2" />
      <path d="M10 5v14" />
      <path d="M6.8 9.5 8.8 12l-2 2.5" />
    </template>
    <template v-else-if="name === 'panel-open'">
      <rect x="4" y="5" width="16" height="14" rx="2" />
      <path d="M10 5v14" />
      <path d="m6.8 9.5 2 2.5-2 2.5" />
    </template>
    <template v-else-if="name === 'brand'">
      <rect x="8.2" y="4.2" width="8.8" height="8.8" rx="2" fill="currentColor" stroke="none" opacity="0.42" />
      <rect x="4.2" y="10.8" width="8.8" height="8.8" rx="2" fill="currentColor" stroke="none" />
    </template>
    <template v-else-if="name === 'sun'">
      <circle cx="12" cy="12" r="3.2" />
      <path d="M12 2.8v2.2M12 19v2.2M4.1 4.1l1.6 1.6M18.3 18.3l1.6 1.6M2.8 12h2.2M19 12h2.2M4.1 19.9l1.6-1.6M18.3 5.7l1.6-1.6" />
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
      <path d="M12 2.8 18.2 6.2v7.6L12 20.2 5.8 13.8V6.2L12 2.8Z" />
      <circle cx="12" cy="12.8" r="2.4" />
      <path d="M12 9.8V8M9.4 10.8l1.4 1.2M14.6 10.8l-1.4 1.2M7.2 12.8h1.8M16.8 12.8h-1.8" />
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
    <template v-else-if="name === 'check'">
      <path d="m5.5 12.2 3.8 3.8L18.5 6.5" />
    </template>
    <template v-else-if="name === 'info'">
      <circle cx="12" cy="12" r="8.2" />
      <path d="M12 10.2V16.2M12 7.8h.01" />
    </template>
    <template v-else-if="name === 'bell'">
      <path d="M12 4.2c-2.2 0-4 1.8-4 4v2.4l-1.4 2.2h11l-1.4-2.2V8.2c0-2.2-1.8-4-4-4Z" />
      <path d="M10 18.2h4" />
    </template>
    <template v-else-if="name === 'tag'">
      <path d="M4.2 12.2 12 4.4l7.8 7.8-3.6 3.6H7.8L4.2 12.2Z" />
      <circle cx="14.6" cy="9.4" r="1" />
    </template>
    <template v-else-if="name === 'spark'">
      <path d="M12 3.5v3.2M12 17.3v3.2M4.2 12h3.2M16.6 12h3.2M6.4 6.4l2.3 2.3M15.3 15.3l2.3 2.3M6.4 17.6l2.3-2.3M15.3 8.7l2.3-2.3" />
    </template>
    <template v-else-if="name === 'nodes'">
      <circle cx="6.5" cy="6.5" r="2.2" />
      <circle cx="17.5" cy="6.5" r="2.2" />
      <circle cx="12" cy="17.5" r="2.2" />
      <path d="M8.4 7.8 10.4 15.2M15.6 7.8l-2 7.4M8.7 6.5h6.6" />
    </template>
    <template v-else-if="name === 'box'">
      <path d="M4.8 8.2 12 4.2l7.2 4v7.6l-7.2 4-7.2-4V8.2Z" />
      <path d="M12 12.2V20.2M4.8 8.2 12 12.2l7.2-4" />
    </template>
    <template v-else-if="name === 'link'">
      <path d="M9.2 14.8a3.4 3.4 0 0 0 4.8 0l2.2-2.2a3.4 3.4 0 0 0-4.8-4.8l-1 1" />
      <path d="M14.8 9.2a3.4 3.4 0 0 0-4.8 0l-2.2 2.2a3.4 3.4 0 0 0 4.8 4.8l1-1" />
    </template>
    <template v-else-if="name === 'alert'">
      <path d="M12 4.2 20.2 18.2H3.8L12 4.2Z" />
      <path d="M12 9.2v4.2M12 16.2h.01" />
    </template>
    <template v-else-if="name === 'folder'">
      <path d="M4.2 6.8h5.2l1.6 1.6h8.8a1.2 1.2 0 0 1 1.2 1.2v8.4a1.2 1.2 0 0 1-1.2 1.2H5.4a1.2 1.2 0 0 1-1.2-1.2V8a1.2 1.2 0 0 1 1-1.2Z" />
    </template>
    <template v-else-if="name === 'list'">
      <path d="M7.5 7.2h10.2M7.5 12h10.2M7.5 16.8h10.2M5 7.2h.01M5 12h.01M5 16.8h.01" />
    </template>
  </svg>
</template>
