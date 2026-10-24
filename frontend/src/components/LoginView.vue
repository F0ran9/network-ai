<template>
  <div class="login-screen">
    <!-- 氛围层: 渐变网格 + 网格纹理, 与机柜头部同源 -->
    <div class="login-atmosphere" aria-hidden="true"></div>

    <div class="login-card" role="form" aria-label="平台登录">
      <div class="login-brand">
        <div class="brand-logo">
          <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <rect x="2.5" y="13.5" width="19" height="7" rx="1.5"/>
            <circle cx="6.5" cy="17" r="1" fill="currentColor" stroke="none"/>
            <circle cx="10" cy="17" r="1" fill="currentColor" stroke="none"/>
            <path d="M12 13.5v-3M6 13.5V8a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v5.5M12 10.5h.01"/>
            <rect x="9" y="3" width="6" height="3" rx="1"/>
          </svg>
        </div>
        <div>
          <h1>网络拓扑配置生成器</h1>
          <span class="login-sub">TOPO · CONFIG · DEPLOY</span>
        </div>
      </div>

      <div class="login-divider" aria-hidden="true"></div>

      <form @submit.prevent="doLogin">
        <label class="field-label" for="login-password">访问密码</label>
        <el-input
          id="login-password"
          v-model="password"
          type="password"
          size="large"
          placeholder="请输入平台密码"
          show-password
          :prefix-icon="Lock"
          autocomplete="current-password"
          autofocus
        />
        <el-button
          class="login-btn"
          type="primary"
          size="large"
          native-type="submit"
          :loading="loading"
          :disabled="!password"
        >
          {{ loading ? '正在验证...' : '进入平台' }}
        </el-button>
      </form>

      <p class="login-hint" v-if="hintShown">首次启动自动生成随机密码，见后端启动日志或 backend/.env 的 APP_PASSWORD；登录后可在【设置 → 全局参数设置 → 平台登录密码】中修改</p>
    </div>

    <footer class="login-footer">
      <span class="status-led"><span class="led"></span>SYSTEM READY</span>
    </footer>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Lock } from '@element-plus/icons-vue'
import axios from 'axios'

const emit = defineEmits(['login'])
const password = ref('')
const loading = ref(false)
const hintShown = ref(false)

async function doLogin() {
  if (!password.value || loading.value) return
  loading.value = true
  try {
    const res = await axios.post('/api/auth/login', { password: password.value })
    localStorage.setItem('tct-token', res.data.token)
    ElMessage.success('登录成功')
    emit('login')
  } catch (err) {
    hintShown.value = true
    ElMessage.error(err.response?.data?.detail || '登录失败，请检查网络')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-screen {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: grid;
  place-items: center;
  background: var(--tct-rack-bg);
}
/* 氛围层: 双径向渐变网格 + 细网格纹理 */
.login-atmosphere {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(56rem 40rem at 14% -8%, rgba(14, 116, 144, 0.30), transparent 60%),
    radial-gradient(48rem 36rem at 96% 4%, rgba(240, 167, 46, 0.10), transparent 55%),
    repeating-linear-gradient(0deg, transparent 0 39px, rgba(148, 187, 208, 0.05) 39px 40px),
    repeating-linear-gradient(90deg, transparent 0 39px, rgba(148, 187, 208, 0.05) 39px 40px);
}
.login-card {
  position: relative;
  width: min(400px, calc(100vw - 32px));
  padding: 32px 28px 24px;
  background: var(--tct-panel);
  border: 1px solid var(--tct-border-strong);
  border-radius: var(--tct-radius-lg);
  box-shadow: var(--tct-shadow-3);
}
/* 卡片顶部琥珀发丝线 — 与品牌图标同色 */
.login-card::before {
  content: "";
  position: absolute;
  top: 0;
  left: 24px;
  right: 24px;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--tct-accent), transparent);
}
.login-brand {
  display: flex;
  align-items: center;
  gap: 12px;
}
.brand-logo {
  width: 42px;
  height: 42px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  color: var(--tct-accent);
  background: rgba(240, 167, 46, 0.10);
  border: 1px solid rgba(240, 167, 46, 0.28);
  border-radius: var(--tct-radius);
}
.login-brand h1 {
  margin: 0;
  font-family: var(--tct-mono);
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--tct-ink);
}
.login-sub {
  font-family: var(--tct-mono);
  font-size: 10px;
  letter-spacing: 0.22em;
  color: var(--tct-muted);
}
.login-divider {
  height: 1px;
  background: var(--tct-border);
  margin: 20px 0;
}
.field-label {
  display: block;
  font-family: var(--tct-mono);
  font-size: var(--tct-fs-xs);
  letter-spacing: 0.12em;
  color: var(--tct-muted);
  margin-bottom: 8px;
}
.login-btn {
  width: 100%;
  margin-top: 14px;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.login-hint {
  margin: 14px 0 0;
  font-size: var(--tct-fs-xs);
  line-height: 1.7;
  color: var(--tct-muted);
}
.login-footer {
  position: absolute;
  bottom: 20px;
  left: 0;
  right: 0;
  display: flex;
  justify-content: center;
}
/* 复用头部状态灯样式 (login-screen 不在 scoped App 树内, 需本地定义) */
.status-led {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border: 1px solid rgba(148, 187, 208, 0.18);
  border-radius: 999px;
  font-family: var(--tct-mono);
  font-size: 10px;
  letter-spacing: 0.14em;
  color: rgba(148, 187, 208, 0.7);
}
.status-led .led {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--tct-ok);
  box-shadow: 0 0 6px var(--tct-ok);
}
@media (prefers-reduced-motion: no-preference) {
  .status-led .led { animation: led-breathe 2.4s ease-in-out infinite; }
  .login-card { animation: card-in var(--tct-dur-base) var(--tct-ease) both; }
}
@keyframes led-breathe {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.45; }
}
@keyframes card-in {
  from { opacity: 0; transform: translateY(18px); }
  to   { opacity: 1; transform: none; }
}
@media (prefers-reduced-motion: reduce) {
  .login-card, .status-led .led { animation: none; }
}
</style>
