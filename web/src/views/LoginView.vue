<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { login } from "../api";
import Icon from "../components/Icon.vue";

const REMEMBER_KEY = "zhiyu-login-user";

const router = useRouter();
const route = useRoute();
const username = ref("");
const password = ref("");
const remember = ref(false);
const showPassword = ref(false);
const pending = ref(false);
const submitted = ref(false);
const authError = ref("");
const userError = ref("");
const passError = ref("");
const recoverHint = ref("");
const summary = ref<HTMLElement | null>(null);
const banner = computed(() => {
  if (authError.value) return authError.value;
  if (userError.value && passError.value) return "请填写用户名和密码";
  return userError.value || passError.value;
});

onMounted(() => {
  const saved = localStorage.getItem(REMEMBER_KEY);
  if (saved) {
    username.value = saved;
    remember.value = true;
  }
});

function checkFields() {
  userError.value = username.value.trim() ? "" : "请填写用户名";
  passError.value = password.value ? "" : "请填写密码";
  return !userError.value && !passError.value;
}

function onForgot() {
  recoverHint.value = "本机版本不提供找回密码，请联系管理员重置。";
}

async function submit() {
  submitted.value = true;
  authError.value = "";
  recoverHint.value = "";
  if (!checkFields()) {
    await nextTick();
    summary.value?.focus();
    return;
  }
  pending.value = true;
  try {
    await login(username.value.trim(), password.value);
    if (remember.value) {
      localStorage.setItem(REMEMBER_KEY, username.value.trim());
    } else {
      localStorage.removeItem(REMEMBER_KEY);
    }
    const next = typeof route.query.redirect === "string" ? route.query.redirect : "/";
    await router.replace(next);
  } catch (e) {
    authError.value = e instanceof Error ? e.message : "登录失败";
    await nextTick();
    summary.value?.focus();
  } finally {
    pending.value = false;
  }
}
</script>

<template>
  <main class="login-page">
    <div class="stage">
      <article class="sheet" aria-label="登录">
        <section class="brand" aria-label="知域介绍">
          <div class="logo-row">
            <span class="mark" aria-hidden="true"></span>
            <div>
              <p class="product">知域</p>
              <p class="slogan">你的私人知识助手</p>
            </div>
          </div>
          <h1>
            在<span class="hl">知识</span>的领域<br />
            探索无限可能
          </h1>
          <p class="pitch">
            知域，帮助你高效管理知识、智能检索信息，让每一次提问都有价值的答案。
          </p>
          <ul class="points">
            <li>
              <span class="pt-ico" aria-hidden="true"><Icon name="search" /></span>
              多维度检索，答案标注引用来源
            </li>
            <li>
              <span class="pt-ico" aria-hidden="true"><Icon name="chat" /></span>
              Agent 任务协作，自动查库作答
            </li>
            <li>
              <span class="pt-ico" aria-hidden="true"><Icon name="lock" /></span>
              数据全部保存在本机，隐私可控
            </li>
          </ul>
          <img class="hero" src="/login-hero.jpg" alt="" width="640" height="640" />
        </section>

        <form class="form" @submit.prevent="submit" novalidate>
          <h2>欢迎回来</h2>
          <p class="lede">登录知域，继续你的知识探索之旅</p>

          <p
            id="login-banner"
            ref="summary"
            class="summary"
            :class="{ on: !!banner }"
            :role="banner ? 'alert' : undefined"
            tabindex="-1"
          >{{ banner }}</p>

          <div class="field">
            <label for="login-username">用户名</label>
            <div class="control">
              <span class="lead-ico" aria-hidden="true"><Icon name="user" /></span>
              <input
                id="login-username"
                v-model.trim="username"
                name="username"
                autocomplete="username"
                placeholder="用户名"
                required
                :aria-invalid="submitted && !!userError"
                :aria-describedby="submitted && userError ? 'login-banner' : undefined"
                @blur="submitted && checkFields()"
              />
            </div>
          </div>

          <div class="field">
            <label for="login-password">密码</label>
            <div class="control">
              <span class="lead-ico" aria-hidden="true"><Icon name="lock" /></span>
              <input
                id="login-password"
                v-model="password"
                name="password"
                :type="showPassword ? 'text' : 'password'"
                autocomplete="current-password"
                placeholder="密码"
                required
                :aria-invalid="submitted && !!passError"
                :aria-describedby="submitted && (passError || authError) ? 'login-banner' : undefined"
                @blur="submitted && checkFields()"
              />
              <button
                class="reveal"
                type="button"
                :aria-pressed="showPassword"
                :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                @click="showPassword = !showPassword"
              >
                <Icon :name="showPassword ? 'eyeOff' : 'eye'" />
              </button>
            </div>
          </div>

          <div class="row">
            <label class="remember">
              <input v-model="remember" type="checkbox" />
              记住我
            </label>
            <button class="linkish" type="button" @click="onForgot">忘记密码?</button>
          </div>
          <p v-if="recoverHint" class="hint" role="status">{{ recoverHint }}</p>

          <button class="btn btn-primary submit" type="submit" :disabled="pending">
            {{ pending ? "正在登录…" : "登录" }}
          </button>

          <p class="foot">
            首次使用知域？暂无法注册入口，如需使用请
            <span class="accent">联系管理员</span>
          </p>
        </form>
      </article>
    </div>

    <p class="legal">知域 · 你的私人知识助手　© 2024 知域. All rights reserved.</p>
  </main>
</template>

<style scoped>
.login-page {
  position: relative;
  min-height: 100dvh;
  display: grid;
  place-items: center;
  padding: 2.5rem 1.25rem 3.5rem;
  overflow: hidden;
  background:
    linear-gradient(180deg, rgba(240, 244, 255, 0.55) 0%, rgba(255, 255, 255, 0.35) 100%),
    url("/login-scene.jpg") center / cover no-repeat #f0f4ff;
  color: #333;
}
.stage {
  position: relative;
  width: min(58rem, 100%);
  display: grid;
  place-items: center;
}
.sheet {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(17.5rem, 0.95fr);
  width: 100%;
  background: #fff;
  border-radius: 18px;
  box-shadow: 0 24px 60px rgba(45, 92, 247, 0.12), 0 2px 10px rgba(15, 23, 42, 0.06);
  overflow: hidden;
}
.brand {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 2rem 2rem 1.25rem;
  background:
    radial-gradient(ellipse at 20% 0%, rgba(74, 128, 255, 0.08), transparent 50%),
    linear-gradient(165deg, #f8fbff 0%, #eef4ff 100%);
}
.logo-row {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  margin-bottom: 1.4rem;
}
.mark {
  width: 2rem;
  height: 2rem;
  position: relative;
  flex-shrink: 0;
}
.mark::before,
.mark::after {
  content: "";
  position: absolute;
  width: 1.1rem;
  height: 1.1rem;
  border-radius: 4px;
  background: #2d5cf7;
}
.mark::before {
  top: 0;
  left: 0.4rem;
  opacity: 0.4;
}
.mark::after {
  bottom: 0;
  left: 0;
}
.product {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 700;
  line-height: 1.2;
}
.slogan {
  margin: 0.12rem 0 0;
  font-size: 0.78rem;
  color: #666;
  line-height: 1.4;
}
.brand h1 {
  margin: 0 0 0.85rem;
  font-size: clamp(1.45rem, 2.6vw, 1.95rem);
  font-weight: 750;
  letter-spacing: -0.03em;
  line-height: 1.3;
}
.hl {
  color: #2d5cf7;
}
.pitch {
  margin: 0;
  max-width: 22rem;
  font-size: 0.88rem;
  line-height: 1.7;
  color: #666;
}
.points {
  list-style: none;
  margin: 1.1rem 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}
.points li {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  font-size: 0.82rem;
  color: #475569;
}
.pt-ico {
  width: 1.7rem;
  height: 1.7rem;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: #dbeafe;
  color: #2d5cf7;
}
.pt-ico :deep(.ico) {
  width: 0.95rem;
  height: 0.95rem;
}
.hero {
  display: block;
  width: min(15rem, 80%);
  height: auto;
  margin: auto auto 0.25rem 0;
  pointer-events: none;
}
.form {
  padding: 2.1rem 1.85rem 1.6rem;
}
.form h2 {
  margin: 0 0 0.35rem;
  font-size: 1.55rem;
  letter-spacing: -0.03em;
  line-height: 1.25;
}
.lede {
  margin: 0 0 0.45rem;
  font-size: 0.88rem;
  line-height: 1.5;
  color: #666;
}
.summary {
  margin: 0 0 0.85rem;
  min-height: 1.5rem;
  font-size: 0.82rem;
  line-height: 1.5;
  color: transparent;
  outline: none;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.summary.on {
  color: var(--danger);
}
.summary:focus-visible {
  box-shadow: 0 0 0 2px #fff, 0 0 0 4px #2d5cf7;
}
.field {
  margin-bottom: 0.9rem;
}
.field label {
  display: block;
  font-size: 0.85rem;
  font-weight: 550;
  margin-bottom: 0.38rem;
}
.control {
  position: relative;
}
.control input {
  width: 100%;
  min-height: 2.7rem;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 0.55rem 2.75rem 0.55rem 2.55rem;
  font: inherit;
  font-size: 0.95rem;
  background: #fff;
  color: #333;
}
.control input::placeholder {
  color: #94a3b8;
}
.control input:focus-visible {
  outline: none;
  border-color: #2d5cf7;
  box-shadow: 0 0 0 3px rgba(45, 92, 247, 0.16);
}
.control input[aria-invalid="true"] {
  border-color: var(--danger);
}
.lead-ico {
  position: absolute;
  left: 0.1rem;
  top: 50%;
  transform: translateY(-50%);
  width: 2.4rem;
  height: 2.4rem;
  display: grid;
  place-items: center;
  color: #94a3b8;
  pointer-events: none;
}
.lead-ico :deep(.ico) {
  width: 1.05rem;
  height: 1.05rem;
}
.reveal {
  position: absolute;
  right: 0.05rem;
  top: 50%;
  transform: translateY(-50%);
  width: 2.7rem;
  height: 2.7rem;
  display: grid;
  place-items: center;
  border: none;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  border-radius: 10px;
}
.reveal:hover {
  color: #333;
}
.reveal:focus-visible {
  outline: 2px solid #2d5cf7;
  outline-offset: -2px;
}
.reveal :deep(.ico) {
  width: 1.1rem;
  height: 1.1rem;
}
.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin: 0.15rem 0 1rem;
}
.remember {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.82rem;
  color: #555;
  cursor: pointer;
}
.remember input {
  width: 0.95rem;
  height: 0.95rem;
  accent-color: #2d5cf7;
}
.linkish {
  border: none;
  background: none;
  padding: 0;
  font: inherit;
  font-size: 0.82rem;
  color: #2d5cf7;
  cursor: pointer;
}
.linkish:hover {
  text-decoration: underline;
}
.hint {
  margin: -0.55rem 0 0.85rem;
  font-size: 0.78rem;
  color: #666;
  line-height: 1.45;
}
.submit {
  width: 100%;
  min-height: 2.75rem;
  justify-content: center;
  font-size: 0.95rem;
  border: none;
  border-radius: 10px;
  background: linear-gradient(180deg, #4a80ff 0%, #2d5cf7 100%);
  color: #fff;
  box-shadow: 0 8px 18px rgba(45, 92, 247, 0.28);
  transition: filter 0.18s ease;
}
.submit:hover:not(:disabled) {
  filter: brightness(1.04);
}
.foot {
  margin: 1.15rem 0 0;
  font-size: 0.75rem;
  line-height: 1.55;
  color: #888;
  text-align: center;
}
.accent {
  color: #2d5cf7;
}
.legal {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 1rem;
  margin: 0;
  text-align: center;
  font-size: 0.72rem;
  color: #94a3b8;
}
@media (prefers-reduced-motion: reduce) {
  .submit {
    transition: none;
  }
}
@media (max-width: 900px) {
  .sheet {
    grid-template-columns: 1fr;
  }
  .brand {
    padding-bottom: 0.5rem;
  }
  .hero {
    width: min(12rem, 55%);
    margin: 1rem auto 0.5rem;
  }
  .points {
    margin-top: 1rem;
  }
  .form {
    order: -1;
  }
}
::selection {
  background: rgba(45, 92, 247, 0.16);
  color: #333;
}
</style>
