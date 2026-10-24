<template>
  <el-dialog
    v-model="visible"
    width="560px"
    :close-on-click-modal="false"
    class="ai-cfg-dialog"
  >
    <!-- 标题区: 编辑: xxx + 激活徽标 -->
    <template #header>
      <div class="dlg-head">
        <div class="dlg-title">
          编辑：{{ form.name || 'AI 大模型' }}
          <span class="active-badge" :class="{ off: !current.api_key_set }">
            {{ current.api_key_set ? '激活中' : '未配置' }}
          </span>
        </div>
        <p class="dlg-sub">修改后点击保存；激活配置保存后对配置生成 / AI 助手 / 识图立即生效。</p>
      </div>
    </template>

    <div class="cfg-body">
      <!-- 名称 + 格式 -->
      <div class="cfg-row">
        <div class="cfg-field">
          <label>名称</label>
          <el-input v-model="form.name" size="large" placeholder="如 deepseek / glm / siliconflow" />
        </div>
        <div class="cfg-field">
          <label>格式</label>
          <el-select v-model="form.format" size="large" style="width: 100%">
            <el-option label="OpenAI 兼容" value="openai" />
            <el-option label="Anthropic 兼容" value="anthropic" />
          </el-select>
        </div>
      </div>
      <p class="cfg-tip cfg-tip-row">
        大多数国产模型（DeepSeek / GLM / Kimi / SiliconFlow 中转）选 OpenAI 兼容；GLM 也有
        <code>/api/anthropic</code> 端点可选 Anthropic 兼容；Claude 官方选 Anthropic 兼容。
      </p>

      <!-- 模型: 手填 + 自动获取 -->
      <div class="cfg-field">
        <label>模型</label>
        <div class="model-input">
          <el-input v-model="form.model" size="large" :placeholder="current.model || 'deepseek-chat'" />
          <el-button size="large" :loading="fetchingModels" @click="fetchModels" title="从服务商接口获取可用模型列表">
            {{ fetchingModels ? '获取中…' : '自动获取' }}
          </el-button>
        </div>
        <p class="cfg-tip">
          可手动填写，也可点"自动获取"拉取该服务商的模型列表。常用：
          <code>deepseek-chat</code>、<code>glm-4.7</code>、<code>kimi-k2</code> 等。
        </p>
        <el-select
          v-if="modelOptions.length"
          v-model="form.model"
          size="large"
          filterable
          class="model-select"
          placeholder="从列表选择模型"
        >
          <el-option v-for="m in modelOptions" :key="m" :label="m" :value="m" />
        </el-select>
      </div>

      <!-- Base URL -->
      <div class="cfg-field">
        <label>Base URL（可选）</label>
        <el-input v-model="form.baseUrl" size="large" :placeholder="baseUrlPlaceholder" />
        <p class="cfg-tip">{{ baseUrlTip }}</p>
      </div>

      <!-- API Key -->
      <div class="cfg-field">
        <label>API Key</label>
        <el-input
          v-model="form.apiKey"
          size="large"
          type="password"
          show-password
          autocomplete="new-password"
          :placeholder="current.api_key_set ? `已设置（${current.api_key_masked}），留空保持不变` : 'sk-...'"
        />
        <p class="cfg-tip">密钥仅保存在本机 backend/.env，不会上传到任何第三方。</p>
      </div>

      <!-- 连通性测试结果 -->
      <div v-if="testResult" class="test-result" :class="testResult.ok ? 'ok' : 'fail'">
        <span class="test-dot"></span>
        <template v-if="testResult.ok">
          连通正常 <span class="test-detail">模型: {{ testResult.model }} · 格式: {{ testResult.format }}</span>
        </template>
        <template v-else>连接失败：{{ testResult.error }}</template>
      </div>
    </div>

    <template #footer>
      <div class="dlg-foot">
        <el-button @click="visible = false">取消</el-button>
        <el-button :loading="testing" @click="testConn">
          {{ testing ? '测试中…' : '测试连通' }}
        </el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

const visible = ref(false)
const saving = ref(false)
const testing = ref(false)
const fetchingModels = ref(false)
const testResult = ref(null)
const modelOptions = ref([])
const current = reactive({ api_key_set: false, api_key_masked: '', base_url: '', model: '', format: 'openai', name: '' })
const form = reactive({ name: '', format: 'openai', apiKey: '', baseUrl: '', model: '' })

const baseUrlPlaceholder = computed(() =>
  form.format === 'anthropic'
    ? 'https://open.bigmodel.cn/api/anthropic'
    : 'https://api.deepseek.com'
)
const baseUrlTip = computed(() =>
  form.format === 'anthropic'
    ? 'Anthropic 兼容端点地址。例：GLM 填 https://open.bigmodel.cn/api/anthropic；Claude 官方留空即可。'
    : 'OpenAI 兼容端点地址。用 DeepSeek 官方留空即可；GLM 填 https://open.bigmodel.cn/api/paas/v4；走 SiliconFlow 等中转填对应地址。'
)

async function open() {
  visible.value = true
  testResult.value = null
  modelOptions.value = []
  form.apiKey = ''
  form.baseUrl = ''
  form.model = ''
  form.name = ''
  form.format = 'openai'
  try {
    const res = await axios.get('/api/settings')
    Object.assign(current, res.data.provider || {})
    // 预填: 名称/格式/模型回显, key 与 URL 留空(空=保持)
    form.name = current.name || ''
    form.format = current.format || 'openai'
  } catch (_) {
    ElMessage.error('读取配置失败')
  }
}
watch(visible, (v) => { if (v) open() })

function payload() {
  return {
    name: form.name.trim(),
    format: form.format,
    api_key: form.apiKey.trim(),
    base_url: form.baseUrl.trim(),
    model: form.model.trim(),
  }
}

async function ensureSaved() {
  const p = payload()
  if (p.api_key || p.base_url || p.model || p.format !== (current.format || 'openai') || p.name) {
    await axios.post('/api/settings', p)
  }
}

async function save() {
  saving.value = true
  try {
    await axios.post('/api/settings', payload())
    ElMessage.success('已保存并立即生效')
    visible.value = false
  } catch (err) {
    ElMessage.error('保存失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    saving.value = false
  }
}

async function testConn() {
  testing.value = true
  testResult.value = null
  try {
    await ensureSaved()
    testResult.value = (await axios.post('/api/settings/test')).data
  } catch (err) {
    testResult.value = { ok: false, error: err.response?.data?.detail || err.message }
  } finally {
    testing.value = false
  }
}

async function fetchModels() {
  fetchingModels.value = true
  try {
    // 表单里有新值先暂存, 拉取的就是将生效的配置对应的模型列表
    await ensureSaved()
    const res = (await axios.get('/api/settings/models')).data
    if (res.ok && res.models.length) {
      modelOptions.value = res.models
      ElMessage.success(`获取到 ${res.models.length} 个模型，可在下方下拉框选择`)
    } else {
      ElMessage.error('获取失败: ' + (res.error || '服务商未返回模型列表'))
    }
  } catch (err) {
    ElMessage.error('获取失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    fetchingModels.value = false
  }
}
</script>

<style scoped>
/* ============ 标题区 ============ */
.dlg-head { padding: 2px 0; }
.dlg-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 19px;
  font-weight: 700;
  color: var(--tct-fg, #111827);
}
.active-badge {
  font-size: 12px;
  font-weight: 600;
  padding: 2px 10px;
  border-radius: 999px;
  color: #b45309;
  background: rgba(245, 158, 11, 0.14);
  border: 1px solid rgba(245, 158, 11, 0.45);
}
.active-badge.off {
  color: var(--tct-muted, #6b7280);
  background: rgba(107, 114, 128, 0.1);
  border-color: rgba(107, 114, 128, 0.35);
}
.dlg-sub {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--tct-muted, #6b7280);
  line-height: 1.6;
}

/* ============ 表单区 ============ */
.cfg-body { padding-top: 4px; }
.cfg-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.cfg-field { margin-bottom: 16px; }
.cfg-field label {
  display: block;
  font-size: 15px;
  font-weight: 700;
  color: var(--tct-fg, #111827);
  margin-bottom: 7px;
}
.cfg-field :deep(.el-input__wrapper),
.cfg-field :deep(.el-select__wrapper) {
  border-radius: 8px;
}
.cfg-tip {
  margin: 6px 0 0;
  font-size: 12.5px;
  color: var(--tct-muted, #6b7280);
  line-height: 1.7;
}
.cfg-tip-row { margin-top: -8px; margin-bottom: 16px; }
.cfg-tip code {
  font-family: var(--tct-mono);
  font-size: 11.5px;
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--tct-brand-soft, rgba(14, 116, 144, 0.09));
  color: var(--tct-brand, #0e7484);
}
.model-input {
  display: flex;
  gap: 8px;
}
.model-input .el-input { flex: 1; }
.model-select { margin-top: 8px; width: 100%; }

/* ============ 测试结果 ============ */
.test-result {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.5;
}
.test-result.ok {
  color: #15803d;
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.35);
}
.test-result.fail {
  color: #b91c1c;
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.35);
}
.test-dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.test-result.ok .test-dot { background: #22c55e; }
.test-result.fail .test-dot { background: #ef4444; }
.test-detail { color: var(--tct-muted, #6b7280); }

/* ============ 底部按钮 ============ */
.dlg-foot {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
.dlg-foot .el-button + .el-button { margin-left: 0; }
</style>
