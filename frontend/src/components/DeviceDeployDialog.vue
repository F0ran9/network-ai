<template>
  <el-dialog
    v-model="visible"
    title="真机下发与连通性验收"
    width="880px"
    :close-on-click-modal="false"
    class="deploy-dialog"
    append-to-body
  >
    <!-- 连接信息 (单台模式共享) -->
    <div class="section">
      <div class="section-title">连接信息 <span class="form-tip">批量模式下仅"设备类型 / 用户名 / 密码 / 端口"生效</span></div>
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

      <!-- Tab 2: 批量下发 -->
      <el-tab-pane :label="`批量下发 (${batchSelected.length})`" name="batch">
        <el-alert type="info" :closable="false" show-icon style="margin-bottom:10px">
          勾选多台设备按<strong>核心 → 汇聚 → 接入 → 终端</strong>顺序逐台推送（SSH 账号共用）。
          管理 IP 自动取自画布设备的"管理 IP"属性, 可手动修正; 建议先用 dry-run 整批预览。
        </el-alert>
        <div class="push-bar">
          <el-button size="small" @click="batchSelectAll(true)">全选</el-button>
          <el-button size="small" @click="batchSelectAll(false)">全不选</el-button>
          <el-switch v-model="batchDryRun" active-text="dry-run 预览" inactive-text="真实下发" size="small" />
          <el-tag :type="batchDryRun ? 'info' : 'danger'" effect="dark" size="small">
            {{ batchDryRun ? '不会改动设备' : '将批量真实修改!' }}
          </el-tag>
          <el-checkbox v-model="stopOnError" size="small">失败即中止</el-checkbox>
          <div class="push-actions">
            <el-button type="primary" :loading="batchRunning" :disabled="!batchSelected.length"
              @click="startBatch">
              {{ batchRunning ? '下发中…' : (batchDryRun ? '批量预览' : '批量下发') }}
            </el-button>
          </div>
        </div>

        <el-table :data="batchRows" size="small" max-height="280" style="width:100%"
          @selection-change="onBatchSelectionChange" ref="batchTableRef">
          <el-table-column type="selection" width="40" />
          <el-table-column label="#" width="42">
            <template #default="{ $index }">{{ $index + 1 }}</template>
          </el-table-column>
          <el-table-column prop="name" label="设备" min-width="150">
            <template #default="{ row }">{{ formatDeviceName(row.key) }}</template>
          </el-table-column>
          <el-table-column label="角色" width="80">
            <template #default="{ row }">
              <el-tag size="small" type="info">{{ roleName(row.role) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="管理 IP" min-width="150">
            <template #default="{ row }">
              <el-input v-model="row.host" size="small" placeholder="未填写"
                :class="{ 'host-missing': !row.host }" />
            </template>
          </el-table-column>
          <el-table-column label="命令数" width="70">
            <template #default="{ row }">{{ (configs[row.key] || []).length }}</template>
          </el-table-column>
          <el-table-column label="结果" min-width="120">
            <template #default="{ row }">
              <el-tag v-if="row.status === 'success'" type="success" size="small">下发成功</el-tag>
              <el-tag v-else-if="row.status === 'dry-run'" type="info" size="small">预览 OK</el-tag>
              <el-tag v-else-if="row.status === 'fail'" type="danger" size="small">失败</el-tag>
              <span v-if="row.message" class="form-tip batch-msg">{{ row.message }}</span>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="batchLog.length" class="scan-log">
          <div v-for="(l, i) in batchLog" :key="i" class="log-line" :class="l.startsWith('⛔') ? 'err' : ''">{{ l }}</div>
          <div v-if="batchRunning" class="log-line scanning">批量下发中…</div>
        </div>
        <div v-if="batchSummary" class="result-box">
          <el-alert :type="batchSummary.fail ? 'warning' : 'success'" :closable="false" show-icon
            :title="`批量完成: ${batchSummary.done}/${batchSummary.total} 台执行, 成功 ${batchSummary.ok}, 失败 ${batchSummary.fail}`
              + (batchSummary.skipped ? `, 中止跳过 ${batchSummary.skipped}` : '')" />
        </div>
      </el-tab-pane>

      <!-- Tab 3: 连通性验收 -->
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

      <!-- Tab 4: 备份回滚 -->
      <el-tab-pane label="备份回滚" name="rollback">
        <el-alert type="warning" :closable="false" show-icon style="margin-bottom:10px">
          将所选备份的内容推回设备（恢复到该时间点的配置）。回滚前会<strong>先备份当前配置</strong>，
          且建议先用 dry-run 预览。回放的是完整 running-config, 请确认设备型号与备份来源一致。
        </el-alert>
        <div class="push-bar">
          <el-button size="small" :loading="backupsLoading" @click="loadBackups" :disabled="!host">
            刷新备份列表
          </el-button>
          <span v-if="!host" class="form-tip">请先在上方填写管理 IP</span>
          <div class="push-actions">
            <el-switch v-model="rbDryRun" active-text="dry-run 预览" inactive-text="真实回滚" size="small" />
            <el-button type="warning" :loading="rbRunning" :disabled="!rbSelected || !host" @click="doRollback">
              {{ rbDryRun ? '预览回滚' : '确认回滚' }}
            </el-button>
          </div>
        </div>

        <el-table :data="backups" size="small" max-height="240" style="width:100%"
          highlight-current-row @current-change="rbSelected = $event?.file || ''">
          <el-table-column prop="time" label="备份时间" width="160" />
          <el-table-column prop="file" label="文件名" min-width="220" />
          <el-table-column label="大小" width="90">
            <template #default="{ row }">{{ (row.size / 1024).toFixed(1) }} KB</template>
          </el-table-column>
        </el-table>
        <div v-if="rbSelected" class="result-line">已选择: {{ rbSelected }}</div>

        <div v-if="rbResult" class="result-box">
          <el-alert
            :type="rbResult.status === 'success' ? 'success' : 'error'"
            :title="rbResult.status === 'success' ? (rbDryRun ? '回滚预览完成' : '回滚完成') : '回滚失败'"
            :closable="false" show-icon
          />
          <div v-if="rbResult.backup_file" class="result-line">回滚前备份: {{ rbResult.backup_file }}</div>
          <pre v-if="rbResult.commands" class="code-block"><code>{{ rbResult.commands.join('\n') }}</code></pre>
          <pre v-if="rbResult.output_tail" class="code-block"><code>{{ rbResult.output_tail }}</code></pre>
        </div>
      </el-tab-pane>

      <!-- Tab 5: 审计日志 -->
      <el-tab-pane label="审计日志" name="audit">
        <div class="push-bar">
          <el-button size="small" :loading="auditLoading" @click="loadAudit">刷新</el-button>
          <span class="form-tip">记录登录 / 下发 / 回滚 / 验收 / 扫描等全部真机操作, 服务端存于 backend/audit.log</span>
        </div>
        <el-table :data="auditRows" size="small" max-height="360" style="width:100%">
          <el-table-column prop="time" label="时间" width="150" />
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="AUDIT_ACTION[row.action]?.type || 'info'">
                {{ AUDIT_ACTION[row.action]?.name || row.action }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="host" label="设备/IP" min-width="120" />
          <el-table-column label="结果" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.result === 'success' ? 'success' : row.result === 'fail' ? 'danger' : 'info'">
                {{ row.result === 'success' ? '成功' : row.result === 'fail' ? '失败' : row.result === 'dry-run' ? '预览' : row.result }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="detail" label="详情" min-width="200" show-overflow-tooltip />
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
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

const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem('tct-token') || ''}` })

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

// ---- 单台下发 ----
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
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
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
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
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

// ---- 批量下发 ----
// 角色权重: 越小越先下发 (核心先行, 终端最后)
const ROLE_WEIGHT = { router: 0, security: 0, core: 1, aggregation: 2, access: 3, wireless: 4, endpoint: 9 }
const ROLE_NAME = { router: '路由', security: '安全', core: '核心', aggregation: '汇聚', access: '接入', wireless: '无线', endpoint: '终端' }
function roleName(r) { return ROLE_NAME[r] || '其他' }

const batchTableRef = ref(null)
const batchSelected = ref([])
const batchDryRun = ref(true)
const stopOnError = ref(false)
const batchRunning = ref(false)
const batchLog = ref([])
const batchSummary = ref(null)

const batchRows = computed(() => {
  // 节点信息来源: 优先 props.topology (生成配置时的快照),
  // 为空时回退到画布实时模型 (页面刷新后 props.topology 丢失的场景)
  let topoNodes = (props.topology && props.topology.nodes) || {}
  if (!Object.keys(topoNodes).length && typeof window !== 'undefined' && window.__topoDiagram) {
    topoNodes = {}
    for (const n of (window.__topoDiagram.model.nodeDataArray || [])) {
      if (n.category !== 'zone') topoNodes[n.key] = n
    }
  }
  return deviceNames.value
    .map((key) => {
      const node = topoNodes[key]
      return {
        key,
        host: (node && node.mgmtIp) || '',
        role: (node && node.role) || '',
        status: '',
        message: '',
      }
    })
    .sort((a, b) => (ROLE_WEIGHT[a.role] ?? 5) - (ROLE_WEIGHT[b.role] ?? 5))
})

function onBatchSelectionChange(rows) { batchSelected.value = rows }
function batchSelectAll(on) {
  nextTick(() => {
    const t = batchTableRef.value
    if (!t) return
    if (on) t.toggleAllSelection()
    else t.clearSelection()
  })
}

async function startBatch() {
  const devices = batchSelected.value
    .filter((r) => r.host && r.host.trim())
    .map((r) => ({
      name: formatDeviceName(r.key),
      host: r.host.trim(),
      deviceType: deviceType.value,
      commands: (props.configs || {})[r.key] || [],
    }))
  const missing = batchSelected.value.length - devices.length
  if (!devices.length) {
    ElMessage.warning('所选设备均未填写管理 IP (可在设备属性中维护)')
    return
  }
  if (!batchDryRun.value) {
    try {
      await ElMessageBox.confirm(
        `将真实批量修改 ${devices.length} 台设备${missing ? ` (${missing} 台未填 IP 已跳过)` : ''}! 每台下发前会自动备份。确认继续?`,
        '危险操作确认',
        { type: 'warning', confirmButtonText: '开始批量下发', cancelButtonText: '取消' },
      )
    } catch (_) { return }
  } else if (missing) {
    ElMessage.info(`${missing} 台设备未填管理 IP, 已自动跳过`)
  }
  batchRunning.value = true
  batchLog.value = []
  batchSummary.value = null
  try {
    const resp = await fetch('/api/device/push-batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({
        devices,
        username: username.value,
        password: password.value,
        dryRun: batchDryRun.value,
        backup: true,
        port: port.value,
        stopOnError: stopOnError.value,
      }),
    })
    if (!resp.ok) {
      const e = await resp.json().catch(() => ({}))
      throw new Error(e.detail || `HTTP ${resp.status}`)
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const parts = buf.split('\n\n')
      buf = parts.pop()
      for (const p of parts) {
        const line = p.split('\n').find((l) => l.startsWith('data: '))
        if (!line) continue
        const evt = JSON.parse(line.slice(6))
        if (evt.type === 'progress') {
          batchLog.value.push(evt.message)
        } else if (evt.type === 'device') {
          const row = batchSelected.value.find((r) => r.host.trim() === evt.data.host && formatDeviceName(r.key) === evt.data.name)
          if (row) { row.status = evt.data.status; row.message = evt.data.message }
        } else if (evt.type === 'result') {
          batchSummary.value = evt.data
        }
      }
    }
  } catch (e) {
    ElMessage.error(`批量下发失败: ${e.message}`)
  } finally {
    batchRunning.value = false
  }
}

// ---- 备份回滚 ----
const backups = ref([])
const backupsLoading = ref(false)
const rbSelected = ref('')
const rbDryRun = ref(true)
const rbRunning = ref(false)
const rbResult = ref(null)

async function loadBackups() {
  backupsLoading.value = true
  rbSelected.value = ''
  try {
    const resp = await fetch(`/api/device/backups?host=${encodeURIComponent(host.value.trim())}`, { headers: authHeaders() })
    const data = await resp.json()
    if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`)
    backups.value = data.data
    if (!data.data.length) ElMessage.info('该设备暂无备份记录')
  } catch (e) {
    ElMessage.error(`获取备份列表失败: ${e.message}`)
  } finally {
    backupsLoading.value = false
  }
}

async function doRollback() {
  if (!rbDryRun.value) {
    try {
      await ElMessageBox.confirm(
        `将把设备 ${host.value} 的配置回滚到 ${rbSelected.value}!\n回滚前会先备份当前配置。确认继续?`,
        '危险操作确认',
        { type: 'warning', confirmButtonText: '确认回滚', cancelButtonText: '取消' },
      )
    } catch (_) { return }
  }
  rbRunning.value = true
  rbResult.value = null
  try {
    const resp = await fetch('/api/device/rollback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({
        host: host.value,
        deviceType: deviceType.value,
        username: username.value,
        password: password.value,
        backupFile: rbSelected.value,
        dryRun: rbDryRun.value,
        port: port.value,
      }),
    })
    const data = await resp.json()
    if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`)
    rbResult.value = data.data
    ElMessage.success(rbDryRun.value ? '回滚预览完成' : '回滚完成')
  } catch (e) {
    ElMessage.error(`回滚失败: ${e.message}`)
  } finally {
    rbRunning.value = false
  }
}

// ---- 审计日志 ----
const AUDIT_ACTION = {
  login: { name: '登录', type: 'info' },
  'change-password': { name: '改密', type: 'info' },
  push: { name: '下发', type: 'warning' },
  'push-batch': { name: '批量', type: 'warning' },
  rollback: { name: '回滚', type: 'danger' },
  'ping-test': { name: '验收', type: 'success' },
  state: { name: '采集', type: 'info' },
  discover: { name: '扫描', type: 'info' },
}
const auditRows = ref([])
const auditLoading = ref(false)

async function loadAudit() {
  auditLoading.value = true
  try {
    const resp = await fetch('/api/audit?limit=100', { headers: authHeaders() })
    const data = await resp.json()
    if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`)
    auditRows.value = data.data
  } catch (e) {
    ElMessage.error(`获取审计日志失败: ${e.message}`)
  } finally {
    auditLoading.value = false
  }
}

// 打开弹窗或切到审计标签时刷新审计日志
watch(visible, (v) => { if (v && !auditRows.value.length) loadAudit() })
watch(activeTab, (t) => { if (t === 'audit') loadAudit() })
</script>

<style scoped>
.form-tip { font-size: 11px; color: #909399; }
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
.scan-log {
  max-height: 140px; overflow-y: auto; margin-top: 10px;
  background: #10232e; color: #b7d6e2; border-radius: 6px;
  font-family: Consolas, monospace; font-size: 12px;
  padding: 8px 12px;
}
.log-line { line-height: 1.8; }
.log-line.err { color: #f56c6c; }
.log-line.scanning { color: #e6a23c; animation: blink 1.2s infinite; }
@keyframes blink { 50% { opacity: .4; } }
.batch-msg { display: block; }

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
.section-title .form-tip { font-weight: 400; }
.conn-form :deep(.el-form-item) { margin-bottom: 14px; }
.conn-form :deep(.el-form-item__label) {
  padding-bottom: 4px;
  font-size: 12.5px;
  color: #606266;
  line-height: 1.4;
}
.host-missing :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #f56c6c inset; }

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
.push-actions { margin-left: auto; display: flex; gap: 8px; align-items: center; }
</style>
