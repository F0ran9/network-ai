<template>
  <el-dialog
    v-model="visible"
    title="真机下发与连通性验收"
    width="780px"
    :close-on-click-modal="false"
    class="deploy-dialog"
    append-to-body
  >
    <!-- 连接信息 -->
    <div class="section">
      <div class="section-title">连接信息</div>
      <el-form label-position="top" size="default" class="conn-form">
        <el-row :gutter="16">
          <el-col :span="10">
            <el-form-item label="目标设备">
              <el-select v-model="device" placeholder="选择要下发的设备" style="width:100%">
                <el-option
                  v-for="name in deviceNames"
                  :key="name"
                  :label="formatDeviceName(name)"
                  :value="name"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="7">
            <el-form-item label="设备类型">
              <el-select v-model="deviceType" style="width:100%">
                <el-option label="华为 (huawei)" value="huawei" />
                <el-option label="H3C (hp_comware)" value="hp_comware" />
                <el-option label="思科 (cisco_ios)" value="cisco_ios" />
                <el-option label="锐捷 (ruijie_os)" value="ruijie_os" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="7">
            <el-form-item label="SSH 端口">
              <el-input-number v-model="port" :min="1" :max="65535" :controls="false" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="10">
            <el-form-item label="管理 IP">
              <el-input v-model="host" placeholder="如 10.94.89.1" />
            </el-form-item>
          </el-col>
          <el-col :span="7">
            <el-form-item label="用户名">
              <el-input v-model="username" placeholder="SSH 登录账号" />
            </el-form-item>
          </el-col>
          <el-col :span="7">
            <el-form-item label="密码">
              <el-input v-model="password" type="password" show-password placeholder="不保存, 仅本次会话" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </div>

    <el-tabs v-model="activeTab">
      <!-- Tab 1: 配置下发 -->
      <el-tab-pane label="配置下发" name="push">
        <el-alert type="warning" :closable="false" show-icon style="margin-bottom:10px">
          下发前会自动备份设备当前配置到服务器 backups 目录。
          dry-run 只连接并预览将执行的命令，不改动设备。
        </el-alert>
        <div class="push-bar">
          <el-switch v-model="dryRun" active-text="dry-run 预览" inactive-text="真实下发" />
          <el-tag :type="dryRun ? 'info' : 'danger'" effect="dark" size="small">
            {{ dryRun ? '不会改动设备' : '将真实修改设备配置!' }}
          </el-tag>
          <span v-if="selectedCommands.length" class="cmd-count">
            将下发 {{ filteredCommands.length }} 条命令 (已过滤 {{ selectedCommands.length - filteredCommands.length }} 条注释/告警行)
          </span>
          <div class="push-actions">
            <el-button v-if="pushResult" size="small" @click="pushResult = null">清除结果</el-button>
            <el-button type="primary" :loading="pushing" @click="doPush" :disabled="!device || !host">
              {{ dryRun ? '连接并预览' : '确认下发' }}
            </el-button>
          </div>
        </div>

        <div v-if="pushResult" class="result-box">
          <el-alert
            :type="pushResult.status === 'success' ? 'success' : 'error'"
            :title="pushResult.message || (dryRun ? '预览完成' : '下发完成')"
            :closable="false"
            show-icon
          />
          <div v-if="pushResult.backup_file" class="result-line">
            备份文件: {{ pushResult.backup_file }}
          </div>
          <pre v-if="pushResult.commands" class="code-block"><code>{{ pushResult.commands.join('\n') }}</code></pre>
          <pre v-if="pushResult.output_tail" class="code-block"><code>{{ pushResult.output_tail }}</code></pre>
        </div>
      </el-tab-pane>

      <!-- Tab 2: 连通性验收 -->
      <el-tab-pane label="连通性验收" name="test">
        <el-alert type="info" :closable="false" show-icon style="margin-bottom:10px">
          从该设备上以指定源地址 ping 目标 — 验证的是业务网段真实可达，全绿才算"真的通"。
        </el-alert>
        <el-form label-position="top" size="default">
          <el-row :gutter="16">
            <el-col :span="14">
              <el-form-item label="源地址 (从设备哪个接口 IP 发起 ping)">
                <el-input v-model="source" placeholder="VLANIF/管理口 IP, 如 10.94.99.1" />
              </el-form-item>
            </el-col>
            <el-col :span="6">
              <el-form-item label="每目标包数">
                <el-input-number v-model="pingCount" :min="1" :max="20" :controls="false" style="width:100%" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="目标列表 (每行一个: 名称 + IP)">
            <el-input
              v-model="targetsText"
              type="textarea"
              :rows="4"
              placeholder="每行一个: 名称 IP&#10;DHCP服务器 10.94.88.11&#10;内网防火墙 10.94.89.242"
            />
          </el-form-item>
        </el-form>
        <el-button type="primary" :loading="testing" @click="doTest" :disabled="!host || !source || targets.length === 0">
          开始验收测试
        </el-button>

        <div v-if="testResult" class="result-box">
          <el-alert
            :type="testResult.all_pass ? 'success' : 'error'"
            :title="`验收结果: ${testResult.passed}/${testResult.total} 通过 ${testResult.all_pass ? '— 真的通 ✓' : '— 存在不通项!'}`"
            :closable="false"
            show-icon
          />
          <el-table :data="testResult.results" size="small" style="margin-top:8px">
            <el-table-column prop="name" label="目标" min-width="140" />
            <el-table-column prop="ip" label="IP" min-width="120" />
            <el-table-column label="结果" width="90">
              <template #default="{ row }">
                <el-tag :type="row.pass ? 'success' : 'danger'">{{ row.pass ? 'PASS' : 'FAIL' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="detail" label="说明" min-width="120" />
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const props = defineProps({
  modelValue: Boolean,
  configs: Object,
  topology: Object,
})
const emit = defineEmits(['update:modelValue'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// ---- 表单状态 (凭据不记住密码) ----
const SAVED_KEY = 'deploy-conn-info'
const device = ref('')
const deviceType = ref('huawei')
const host = ref('')
const port = ref(22)
const username = ref('')
const password = ref('')

try {
  const saved = JSON.parse(localStorage.getItem(SAVED_KEY) || '{}')
  deviceType.value = saved.deviceType || 'huawei'
  host.value = saved.host || ''
  port.value = saved.port || 22
  username.value = saved.username || ''
} catch (_) {}

watch([deviceType, host, port, username], () => {
  localStorage.setItem(SAVED_KEY, JSON.stringify({
    deviceType: deviceType.value, host: host.value,
    port: port.value, username: username.value,
  }))
})

const deviceNames = computed(() => Object.keys(props.configs || {}))
const activeTab = ref('push')

function formatDeviceName(key) {
  const m = key.match(/^(.+)_(\d+)$/)
  return m ? `${m[1]} #${m[2]}` : key
}

const selectedCommands = computed(() => (props.configs || {})[device.value] || [])
const filteredCommands = computed(() =>
  selectedCommands.value.filter(
    (c) => c.trim() && !c.trim().startsWith(('!', '#')) && !c.includes('WARNING'),
  ),
)

// ---- 下发 ----
const dryRun = ref(true)
const pushing = ref(false)
const pushResult = ref(null)

async function doPush() {
  if (!dryRun.value) {
    try {
      await ElMessageBox.confirm(
        `将真实修改设备 ${host.value} 的配置! 已自动备份当前配置。确认继续?`,
        '危险操作确认',
        { type: 'warning', confirmButtonText: '确认下发', cancelButtonText: '取消' },
      )
    } catch (_) { return }
  }
  pushing.value = true
  pushResult.value = null
  try {
    const resp = await fetch('/api/device/push', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        host: host.value,
        deviceType: deviceType.value,
        username: username.value,
        password: password.value,
        port: port.value,
        commands: selectedCommands.value,
        dryRun: dryRun.value,
        backup: true,
      }),
    })
    const data = await resp.json()
    if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`)
    pushResult.value = data.data
    ElMessage.success(dryRun.value ? '预览完成' : '下发完成')
  } catch (e) {
    ElMessage.error(`下发失败: ${e.message}`)
  } finally {
    pushing.value = false
  }
}

// ---- 连通性验收 ----
const testing = ref(false)
const testResult = ref(null)
const source = ref('')
const pingCount = ref(5)
const targetsText = ref('')

const targets = computed(() =>
  targetsText.value
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => {
      const parts = l.split(/\s+/)
      return parts.length >= 2
        ? { name: parts.slice(0, -1).join(' '), ip: parts[parts.length - 1] }
        : { name: parts[0], ip: parts[0] }
    }),
)

async function doTest() {
  testing.value = true
  testResult.value = null
  try {
    const resp = await fetch('/api/device/ping-tests', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        host: host.value,
        deviceType: deviceType.value,
        username: username.value,
        password: password.value,
        port: port.value,
        source: source.value,
        targets: targets.value,
        count: pingCount.value,
      }),
    })
    const data = await resp.json()
    if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`)
    testResult.value = data.data
    if (data.data.all_pass) ElMessage.success('全部通过, 真的通!')
    else ElMessage.warning(`存在不通项: ${data.data.total - data.data.passed} 个`)
  } catch (e) {
    ElMessage.error(`测试失败: ${e.message}`)
  } finally {
    testing.value = false
  }
}
</script>

<style scoped>
.result-box { margin-top: 12px; }
.result-line { font-size: 12px; color: #606266; margin: 6px 0; }
.cmd-count { font-size: 12px; color: #909399; }
.code-block {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 10px;
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.6;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 260px;
  margin-top: 8px;
}

/* ---- 连接信息分区 ---- */
.section {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 14px 16px 2px;
  margin-bottom: 8px;
  background: #fafbfc;
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: #455a64;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.section-title::before {
  content: '';
  width: 3px;
  height: 13px;
  border-radius: 2px;
  background: #1976d2;
}
.conn-form :deep(.el-form-item) { margin-bottom: 14px; }
.conn-form :deep(.el-form-item__label) {
  padding-bottom: 4px;
  font-size: 12.5px;
  color: #606266;
  line-height: 1.4;
}

/* ---- 配置下发操作条 ---- */
.push-bar {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 14px;
  border: 1px dashed #cfd8dc;
  border-radius: 8px;
  margin-bottom: 12px;
  background: #fafbfc;
  flex-wrap: wrap;
}
.push-actions { margin-left: auto; display: flex; gap: 8px; }
</style>
