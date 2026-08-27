<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { getHealth, getMe, logout, type AppUser } from "../api";
import Icon from "../components/Icon.vue";
import { debugEnabled, setDebugEnabled } from "../debugFlag";

const router = useRouter();
const configured = ref<boolean | null>(null);
const me = ref<AppUser | null>(null);
const leaving = ref(false);
const initial = computed(() => (me.value?.username?.trim().charAt(0) || "?").toUpperCase());
const keyLabel = computed(() => {
  if (configured.value === true) return "已配置";
  if (configured.value === false) return "未配置";
  return "读取中";
});

onMounted(async () => {
  const [h, user] = await Promise.all([getHealth(), getMe().catch(() => null)]);
  configured.value = h.ai_configured;
  me.value = user;
});

async function signOut() {
  leaving.value = true;
  try {
    await logout();
  } finally {
    await router.replace({ name: "login" });
  }
}

function onDebugToggle(ev: Event) {
  const on = (ev.target as HTMLInputElement).checked;
  setDebugEnabled(on);
  if (!on && router.currentRoute.value.name === "debug") {
    router.replace({ name: "settings" });
  }
}
</script>

<template>
  <main class="page settings">
    <header class="head">
      <h1>设置</h1>
      <p class="lede">本机账号与运行环境，数据按用户隔离。</p>
    </header>

    <section class="profile" aria-labelledby="account-title">
      <h2 id="account-title" class="sr">账号</h2>
      <div v-if="me" class="profile-row">
        <span class="face" aria-hidden="true">{{ initial }}</span>
        <div class="id">
          <p class="uname">{{ me.username }}</p>
          <p class="meta">本机登录</p>
        </div>
        <button class="btn out" type="button" :disabled="leaving" @click="signOut">
          {{ leaving ? "正在退出…" : "退出登录" }}
        </button>
      </div>
    </section>

    <section class="panel" aria-labelledby="debug-title">
      <h2 id="debug-title">调试</h2>
      <ul class="rows">
        <li>
          <span class="ico-wrap" aria-hidden="true"><Icon name="bug" /></span>
          <div class="row-main">
            <p class="label">调试模式</p>
            <p class="desc">开启后侧栏出现「调试」，并可进入检索调试页。关闭后菜单与页面均不可见。</p>
          </div>
          <label class="toggle">
            <span class="sr">是否开启调试模式</span>
            <input
              type="checkbox"
              role="switch"
              :checked="debugEnabled"
              :aria-checked="debugEnabled"
              @change="onDebugToggle"
            />
          </label>
        </li>
      </ul>
    </section>

    <section class="panel" aria-labelledby="env-title">
      <h2 id="env-title">环境</h2>
      <ul class="rows">
        <li>
          <span class="ico-wrap" aria-hidden="true"><Icon name="gear" /></span>
          <div>
            <p class="label">
              AI 密钥
              <span class="pill" :class="{ off: configured !== true }">{{ keyLabel }}</span>
            </p>
            <p class="desc">密钥只存在本机环境文件。此页只显示状态，不展示或修改内容。</p>
          </div>
        </li>
        <li>
          <span class="ico-wrap" aria-hidden="true"><Icon name="lock" /></span>
          <div>
            <p class="label">出网说明</p>
            <p class="desc">检索与问答时，文本片段会发往所配置的第三方 AI。原件不会整库上传。</p>
          </div>
        </li>
        <li>
          <span class="ico-wrap" aria-hidden="true"><Icon name="db" /></span>
          <div>
            <p class="label">数据位置</p>
            <p class="desc">知识库与索引在本机 PostgreSQL 与本地文件目录。</p>
          </div>
        </li>
      </ul>
    </section>
  </main>
</template>

<style scoped>
.settings {
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 1.15rem 1.25rem 2rem;
  background: transparent;
}
.head {
  margin-bottom: 1.25rem;
}
.head h1 {
  margin: 0 0 0.35rem;
  font-size: 1.35rem;
  letter-spacing: -0.03em;
  line-height: 1.25;
}
.lede {
  margin: 0;
  font-size: 0.88rem;
  line-height: 1.5;
  color: var(--muted);
}
.sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
.profile {
  margin-bottom: 1rem;
  padding: 1.1rem 1.15rem;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 14px;
  box-shadow: var(--shadow);
}
.profile-row {
  display: flex;
  align-items: center;
  gap: 0.85rem;
}
.face {
  width: 3.25rem;
  height: 3.25rem;
  border-radius: 50%;
  background: var(--teal);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 1.2rem;
  font-weight: 700;
  flex-shrink: 0;
}
.id {
  min-width: 0;
  flex: 1;
}
.uname {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 650;
  line-height: 1.3;
  color: var(--text);
}
.meta {
  margin: 0.2rem 0 0;
  font-size: 0.82rem;
  line-height: 1.4;
  color: var(--muted);
}
.out {
  flex-shrink: 0;
  min-height: 2.5rem;
  padding: 0.45rem 0.9rem;
  background: #fff;
  color: var(--text);
  border: 1px solid var(--line);
  transition: border-color 0.2s ease, color 0.2s ease;
}
.out:hover:not(:disabled) {
  border-color: var(--danger);
  color: var(--danger);
}
.out:focus-visible {
  outline: 2px solid var(--teal);
  outline-offset: 2px;
}
.panel {
  margin-bottom: 1rem;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 14px;
  box-shadow: var(--shadow);
  padding: 1rem 0 0.35rem;
}
.panel h2 {
  margin: 0 1.15rem 0.55rem;
  font-size: 0.72rem;
  font-weight: 650;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
}
.rows {
  list-style: none;
  margin: 0;
  padding: 0;
}
.rows li {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.9rem 1.15rem;
  border-top: 1px solid var(--line);
}
.row-main {
  min-width: 0;
  flex: 1;
}
.ico-wrap {
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 8px;
  background: var(--teal-soft);
  color: var(--teal);
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.ico-wrap :deep(.ico) {
  width: 1.05rem;
  height: 1.05rem;
}
.label {
  margin: 0 0 0.25rem;
  font-size: 0.92rem;
  font-weight: 600;
  line-height: 1.35;
  color: var(--text);
  display: flex;
  align-items: center;
  gap: 0.45rem;
  flex-wrap: wrap;
}
.desc {
  margin: 0;
  font-size: 0.84rem;
  line-height: 1.55;
  color: var(--muted);
}
.pill {
  display: inline-flex;
  align-items: center;
  font-size: 0.7rem;
  font-weight: 600;
  padding: 0.12rem 0.45rem;
  border-radius: 999px;
  background: var(--teal-soft);
  color: var(--teal);
}
.pill.off {
  background: #eee;
  color: #555;
}
.toggle {
  display: inline-flex;
  align-items: center;
  align-self: center;
  gap: 0.4rem;
  cursor: pointer;
  margin: 0;
  flex-shrink: 0;
}
.toggle input {
  appearance: none;
  -webkit-appearance: none;
  width: 2.4rem;
  height: 1.35rem;
  padding: 0;
  margin: 0;
  border: none;
  border-radius: 999px;
  background: #cbd5e1;
  position: relative;
  cursor: pointer;
}
.toggle input::after {
  content: "";
  position: absolute;
  top: 0.15rem;
  left: 0.15rem;
  width: 1.05rem;
  height: 1.05rem;
  border-radius: 50%;
  background: #fff;
}
.toggle input:checked {
  background: var(--teal);
}
.toggle input:checked::after {
  left: 1.2rem;
}
.toggle input:focus-visible {
  outline: 2px solid var(--teal);
  outline-offset: 2px;
}
@media (max-width: 520px) {
  .profile-row {
    flex-wrap: wrap;
  }
  .out {
    width: 100%;
    justify-content: center;
  }
}
@media (prefers-reduced-motion: reduce) {
  .out {
    transition: none;
  }
}
</style>
