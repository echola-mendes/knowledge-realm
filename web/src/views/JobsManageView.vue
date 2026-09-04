<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import {
  createTask,
  deleteTask,
  disableTask,
  enableTask,
  listTaskExecutions,
  listTaskTypes,
  listTasks,
  runTask,
  updateTask,
  type ScheduledTaskItem,
  type TaskExecutionItem,
  type TaskTypeItem,
} from "../api";

const loading = ref(true);
const error = ref("");
const tasks = ref<ScheduledTaskItem[]>([]);
const types = ref<TaskTypeItem[]>([]);
const selectedId = ref<number | null>(null);
const executions = ref<TaskExecutionItem[]>([]);
const execLoading = ref(false);
const busyId = ref<number | null>(null);

const modalOpen = ref(false);
const editing = ref<ScheduledTaskItem | null>(null);
const saving = ref(false);
const modalError = ref("");
const formName = ref("");
const formType = ref("NEWS_REFRESH");
const formSchedule = ref<"INTERVAL" | "CRON">("INTERVAL");
const formMinutes = ref(30);
const formHour = ref(8);
const formMinute = ref(0);

const selected = computed(() => tasks.value.find((t) => t.id === selectedId.value) ?? null);

function typeLabel(taskType: string): string {
  return types.value.find((t) => t.task_type === taskType)?.label ?? taskType;
}

function num(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function scheduleText(task: ScheduledTaskItem): string {
  const cfg = task.schedule_config || {};
  if (task.schedule_type === "INTERVAL") {
    return `每 ${num(cfg.minutes, 30)} 分钟`;
  }
  const hour = String(num(cfg.hour, 0)).padStart(2, "0");
  const minute = String(num(cfg.minute, 0)).padStart(2, "0");
  return `每天 ${hour}:${minute}`;
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("zh-CN", { hour12: false });
}

function resultText(row: TaskExecutionItem): string {
  if (row.error_message) return row.error_message;
  if (row.result && Object.keys(row.result).length) return JSON.stringify(row.result);
  return "—";
}

function statusClass(status: string): string {
  if (status === "SUCCESS") return "ok";
  if (status === "FAILED") return "bad";
  return "wait";
}

async function loadTasks() {
  loading.value = true;
  error.value = "";
  try {
    const [taskRows, typeRows] = await Promise.all([listTasks(), listTaskTypes()]);
    tasks.value = taskRows;
    types.value = typeRows;
    if (selectedId.value == null || !taskRows.some((t) => t.id === selectedId.value)) {
      selectedId.value = taskRows[0]?.id ?? null;
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : "加载失败";
    tasks.value = [];
  } finally {
    loading.value = false;
  }
}

async function loadExecutions() {
  if (selectedId.value == null) {
    executions.value = [];
    return;
  }
  execLoading.value = true;
  try {
    executions.value = await listTaskExecutions(selectedId.value);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "加载执行历史失败";
    executions.value = [];
  } finally {
    execLoading.value = false;
  }
}

function openCreate() {
  editing.value = null;
  formName.value = "";
  formType.value = types.value[0]?.task_type ?? "NEWS_REFRESH";
  formSchedule.value = "INTERVAL";
  formMinutes.value = 30;
  formHour.value = 8;
  formMinute.value = 0;
  modalError.value = "";
  modalOpen.value = true;
}

function openEdit(task: ScheduledTaskItem) {
  editing.value = task;
  formName.value = task.name;
  formType.value = task.task_type;
  formSchedule.value = task.schedule_type;
  formMinutes.value = num(task.schedule_config?.minutes, 30);
  formHour.value = num(task.schedule_config?.hour, 8);
  formMinute.value = num(task.schedule_config?.minute, 0);
  modalError.value = "";
  modalOpen.value = true;
}

function scheduleConfig() {
  if (formSchedule.value === "INTERVAL") {
    return { minutes: Math.max(1, Number(formMinutes.value) || 30) };
  }
  return {
    hour: Math.min(23, Math.max(0, Number(formHour.value) || 0)),
    minute: Math.min(59, Math.max(0, Number(formMinute.value) || 0)),
  };
}

async function saveModal() {
  const name = formName.value.trim();
  if (!name) {
    modalError.value = "请填写名称";
    return;
  }
  saving.value = true;
  modalError.value = "";
  try {
    if (editing.value) {
      await updateTask(editing.value.id, {
        name,
        schedule_type: formSchedule.value,
        schedule_config: scheduleConfig(),
      });
    } else {
      await createTask({
        name,
        task_type: formType.value,
        schedule_type: formSchedule.value,
        schedule_config: scheduleConfig(),
        enabled: true,
      });
    }
    modalOpen.value = false;
    await loadTasks();
  } catch (e) {
    modalError.value = e instanceof Error ? e.message : "保存失败";
  } finally {
    saving.value = false;
  }
}

async function onToggle(task: ScheduledTaskItem) {
  busyId.value = task.id;
  error.value = "";
  try {
    if (task.enabled) await disableTask(task.id);
    else await enableTask(task.id);
    await loadTasks();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "操作失败";
  } finally {
    busyId.value = null;
  }
}

async function onRun(task: ScheduledTaskItem) {
  busyId.value = task.id;
  error.value = "";
  try {
    await runTask(task.id);
    selectedId.value = task.id;
    await Promise.all([loadTasks(), loadExecutions()]);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "执行失败";
  } finally {
    busyId.value = null;
  }
}

async function onDelete(task: ScheduledTaskItem) {
  if (!confirm(`删除任务「${task.name}」？`)) return;
  busyId.value = task.id;
  error.value = "";
  try {
    await deleteTask(task.id);
    if (selectedId.value === task.id) selectedId.value = null;
    await loadTasks();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "删除失败";
  } finally {
    busyId.value = null;
  }
}

watch(selectedId, () => {
  loadExecutions().catch(() => undefined);
});

onMounted(() => {
  loadTasks().catch(() => undefined);
});
</script>

<template>
  <div class="jobs-page">
    <div class="page-head">
      <div>
        <h1>定时任务</h1>
        <p class="sub">调度与执行分离；到点或立即执行都只入队，由 Worker 跑业务。</p>
      </div>
      <button class="btn btn-primary" type="button" @click="openCreate">新建任务</button>
    </div>
    <p v-if="error" class="hint err">{{ error }}</p>

    <div class="card pad list-card">
      <p v-if="loading" class="hint">加载中…</p>
      <ul v-else class="job-list">
        <li
          v-for="task in tasks"
          :key="task.id"
          class="job-row"
          :class="{ on: task.id === selectedId }"
          @click="selectedId = task.id"
        >
          <div class="job-main">
            <div class="job-title">
              <strong>{{ task.name }}</strong>
              <span class="pill soft">{{ typeLabel(task.task_type) }}</span>
              <span class="pill" :class="task.enabled ? 'on' : 'soft'">{{ task.enabled ? "启用" : "停用" }}</span>
            </div>
            <p class="job-meta">
              {{ scheduleText(task) }}
              · 上次 {{ formatTime(task.last_run_at) }}
              · 下次 {{ formatTime(task.next_run_at) }}
            </p>
          </div>
          <span class="ops" @click.stop>
            <button class="btn" type="button" :disabled="busyId === task.id" @click="onRun(task)">立即执行</button>
            <button class="btn" type="button" :disabled="busyId === task.id" @click="onToggle(task)">
              {{ task.enabled ? "停用" : "启用" }}
            </button>
            <button class="btn" type="button" @click="openEdit(task)">编辑</button>
            <button class="btn-danger" type="button" :disabled="busyId === task.id" @click="onDelete(task)">删除</button>
          </span>
        </li>
        <li v-if="!tasks.length" class="empty">暂无定时任务</li>
      </ul>
    </div>

    <div class="card pad exec-card">
      <h2>最近执行{{ selected ? ` · ${selected.name}` : "" }}</h2>
      <p v-if="execLoading" class="hint">加载中…</p>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>时间</th>
              <th>状态</th>
              <th>摘要 / 错误</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in executions" :key="row.id">
              <td>{{ formatTime(row.created_at || row.started_at) }}</td>
              <td><span class="st" :class="statusClass(row.status)">{{ row.status }}</span></td>
              <td class="sum">{{ resultText(row) }}</td>
            </tr>
            <tr v-if="!executions.length">
              <td colspan="3" class="empty">暂无执行记录</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="modalOpen" class="detail-mask" @click.self="modalOpen = false">
      <div class="job-modal" role="dialog" :aria-label="editing ? '编辑任务' : '新建任务'">
        <header class="detail-head">
          <h3>{{ editing ? "编辑任务" : "新建任务" }}</h3>
          <button class="btn" type="button" @click="modalOpen = false">关闭</button>
        </header>
        <p v-if="modalError" class="hint err">{{ modalError }}</p>
        <label class="field">
          <span>名称</span>
          <input v-model="formName" type="text" maxlength="200" />
        </label>
        <label class="field">
          <span>类型</span>
          <select v-model="formType" :disabled="Boolean(editing)">
            <option v-for="item in types" :key="item.task_type" :value="item.task_type">{{ item.label }}</option>
          </select>
        </label>
        <label class="field">
          <span>调度</span>
          <select v-model="formSchedule">
            <option value="INTERVAL">间隔（分钟）</option>
            <option value="CRON">每天定时</option>
          </select>
        </label>
        <label v-if="formSchedule === 'INTERVAL'" class="field">
          <span>间隔分钟</span>
          <input v-model.number="formMinutes" type="number" min="1" />
        </label>
        <div v-else class="cron-row">
          <label class="field">
            <span>时</span>
            <input v-model.number="formHour" type="number" min="0" max="23" />
          </label>
          <label class="field">
            <span>分</span>
            <input v-model.number="formMinute" type="number" min="0" max="59" />
          </label>
        </div>
        <div class="modal-ops">
          <button class="btn" type="button" @click="modalOpen = false">取消</button>
          <button class="btn btn-primary" type="button" :disabled="saving" @click="saveModal">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.jobs-page {
  width: 100%;
  min-width: 0;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
  flex-shrink: 0;
}
.page-head h1 {
  margin: 0 0 0.25rem;
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text);
}
.sub {
  margin: 0;
  color: var(--muted);
  font-size: 0.75rem;
  line-height: 1.5;
}
.hint {
  margin: 0 0 0.6rem;
  font-size: 0.75rem;
  color: var(--muted);
  flex-shrink: 0;
}
.err {
  color: var(--danger);
}
.list-card {
  margin: 0 0 1rem;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.job-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.job-row {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  padding: 0.5rem 0.55rem;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--card);
  cursor: pointer;
}
.job-row.on {
  border-color: var(--teal);
  background: var(--teal-soft);
}
.job-main {
  min-width: 0;
  flex: 1;
}
.job-title {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
}
.job-title strong {
  font-size: 0.78rem;
  font-weight: 600;
}
.job-meta {
  margin: 0.2rem 0 0;
  color: var(--muted);
  font-size: 0.68rem;
}
.ops {
  margin-left: auto;
  display: inline-flex;
  gap: 0.25rem;
  flex-shrink: 0;
}
.exec-card {
  margin: 0;
  flex: 0 0 auto;
  max-height: 40%;
  min-height: 8rem;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.exec-card h2 {
  margin: 0 0 0.4rem;
  font-size: 0.78rem;
}
.table-wrap {
  overflow: auto;
  min-height: 0;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.72rem;
}
th,
td {
  text-align: left;
  padding: 0.35rem 0.4rem;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
}
.empty {
  color: var(--muted);
  padding: 0.6rem 0.2rem;
}
.st.ok {
  color: var(--teal);
  font-weight: 600;
}
.st.bad {
  color: var(--danger);
  font-weight: 600;
}
.st.wait {
  color: var(--muted);
}
.sum {
  word-break: break-all;
}
.detail-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 60;
}
.job-modal {
  width: min(26rem, 94vw);
  background: #fff;
  border-radius: 14px;
  padding: 1rem 1.2rem;
}
.detail-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.6rem;
}
.detail-head h3 {
  margin: 0;
  font-size: 0.95rem;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin-bottom: 0.65rem;
  font-size: 0.72rem;
  color: var(--muted);
}
.field input,
.field select {
  font: inherit;
  color: var(--text);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0.4rem 0.55rem;
  background: #fff;
}
.cron-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.6rem;
}
.modal-ops {
  display: flex;
  justify-content: flex-end;
  gap: 0.4rem;
  margin-top: 0.4rem;
}
</style>
