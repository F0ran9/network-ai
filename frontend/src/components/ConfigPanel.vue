<template>
  <div class="config-panel">
    <div class="panel-header">
      <h3>
        设备配置
        <el-tag v-if="loading" type="warning">生成中...</el-tag>
        <span v-else-if="configCount > 0" class="device-count">({{ configCount }} 台设备)</span>
      </h3>
      <div class="panel-actions" v-if="configCount > 0 && !loading">
        <el-button
          v-if="hasPrevious"
          size="small"
          :type="showDiff ? 'warning' : 'default'"
          @click="showDiff = !showDiff; showCliDiff = false"
        >
          {{ showDiff ? '完整视图' : '差异视图' }}
        </el-button>
        <el-button
          v-if="hasCliDiff"
          size="small"
          :type="showCliDiff ? 'danger' : 'default'"
          @click="showCliDiff = !showCliDiff; showDiff = false"
        >
          {{ showCliDiff ? '完整视图' : 'CLI 变更' }}
        </el-button>
        <el-button size="small" type="primary" :icon="DocumentCopy" @click="copyAllConfigs">
          一键复制全部
        </el-button>
        <el-button size="small" type="danger" :icon="Connection" @click="deployVisible = true">
          下发到设备
        </el-button>
        <el-dropdown @command="handleExport" trigger="click">
          <el-button size="small" type="success" :icon="Download">
            导出配置
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="single">单个文件 (.txt)</el-dropdown-item>
              <el-dropdown-item command="perdevice">每设备独立 (.cfg)</el-dropdown-item>
              <el-dropdown-item command="zip">Zip 压缩包</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- Subnet plan summary -->
    <div v-if="subnetPlan && Object.keys(subnetPlan).length > 0" class="subnet-plan">
      <el-alert type="success" :closable="false" show-icon>
        <template #title>
          子网规划 ({{ Object.keys(subnetPlan).length }} 个 VLAN)
        </template>
        <div class="subnet-grid">
          <div v-for="plan in subnetPlan" :key="plan.vlanId" class="subnet-item">
            <strong>VLAN {{ plan.vlanId }}</strong>:
            网关 {{ plan.gateway }}/{{ plan.prefix }}
            DHCP {{ plan.dhcpStart }}-{{ plan.dhcpEnd }}
          </div>
        </div>
      </el-alert>
    </div>

    <!-- Diff view -->
    <template v-if="showDiff && hasPrevious">
      <div v-for="(cmds, deviceName) in effectiveConfigs" :key="deviceName" class="device-config-block">
        <div class="device-header">
          <h4>{{ formatDeviceName(deviceName) }}</h4>
        </div>
        <pre class="code-block diff-block"><code><span
          v-for="(line, i) in getDeviceDiff(deviceName)"
          :key="i"
          :class="'diff-' + line.type"
        >{{ line.value }}
</span></code></pre>
      </div>
    </template>

    <!-- CLI diff view -->
    <template v-if="showCliDiff && hasCliDiff">
      <div class="diff-summary" v-if="cliDiffSummary">
        <span class="summary-add">+{{ cliDiffSummary.added }}</span>
        <span class="summary-remove">-{{ cliDiffSummary.removed }}</span>
        <span class="summary-devices">{{ cliDiffSummary.deviceCount }} 台设备有变更</span>
      </div>
      <div v-for="(cmds, deviceName) in effectiveConfigs" :key="deviceName" class="device-config-block">
        <div class="device-header">
          <h4>{{ formatDeviceName(deviceName) }}</h4>
        </div>
        <pre class="code-block diff-block"><code><span
          v-for="(line, i) in getCliDeviceDiff(deviceName)"
          :key="i"
          :class="'diff-' + line.type"
        >{{ line.value }}
</span></code></pre>
      </div>
    </template>

    <!-- Full view -->
    <template v-else-if="!showCliDiff">
      <div v-for="(cmds, deviceName) in effectiveConfigs" :key="deviceName" class="device-config-block">
        <div class="device-header">
          <h4>{{ formatDeviceName(deviceName) }}</h4>
          <el-button size="small" text @click="copyCommands(cmds)">复制</el-button>
        </div>
        <pre class="code-block"><code>{{ cmds.join('\n') }}</code></pre>
      </div>
    </template>

    <!-- Version history -->
    <div v-if="history.length > 0 && !loading" class="history-section">
      <el-divider content-position="left">
        <span style="font-size:12px; color:#909399">配置版本历史 ({{ history.length }})</span>
      </el-divider>
      <div class="history-list">
        <div
          v-for="(entry, idx) in history"
          :key="entry.timestamp"
          class="history-entry"
          :class="{ active: compareSnapshot === idx }"
          @click="onHistoryClick(idx)"
        >
          <span class="history-time">{{ entry.label }}</span>
          <span class="history-count">{{ entry.deviceCount }} 台设备</span>
        </div>
      </div>
      <div v-if="compareSnapshot !== null" style="margin-top:6px">
        <el-button size="small" @click="compareSnapshot = null">返回当前版本</el-button>
      </div>
    </div>

    <el-empty v-if="!configs || Object.keys(configs).length===0" description="暂无配置，请绘制拓扑后点击一键生成" />

    <!-- 真机下发与验收 -->
    <DeviceDeployDialog v-model="deployVisible" :configs="configs" :topology="topology" />
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { DocumentCopy, Download, FolderOpened, Connection } from '@element-plus/icons-vue'
import { computeDiff } from '../utils/diff.js'
import JSZip from 'jszip'
import DeviceDeployDialog from './DeviceDeployDialog.vue'

const deployVisible = ref(false)

const props = defineProps({
  configs: Object,
  loading: Boolean,
  topology: Object,
  subnetPlan: Object,
  generatedRef: Object,
})

const HISTORY_KEY = 'topo-config-history'
const history = ref([])
const compareSnapshot = ref(null)

function loadHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    history.value = raw ? JSON.parse(raw).reverse() : []
  } catch (_) { history.value = [] }
}

function onHistoryClick(idx) {
  compareSnapshot.value = compareSnapshot.value === idx ? null : idx
}

loadHistory()
// Reload history when configs change
watch(() => props.configs, () => { loadHistory() }, { deep: true })

const effectiveConfigs = computed(() => {
  if (compareSnapshot.value !== null && history.value[compareSnapshot.value]) {
    return history.value[compareSnapshot.value].configs || {}
  }
  return props.configs || {}
})

const configCount = computed(() => Object.keys(effectiveConfigs.value || {}).length)
const showDiff = ref(false)
const showCliDiff = ref(false)
const previousConfigs = ref({})

// Load previous configs from localStorage
try {
  const saved = localStorage.getItem('topo-configs-prev')
  if (saved) previousConfigs.value = JSON.parse(saved)
} catch (_) {}

const hasPrevious = computed(() => Object.keys(previousConfigs.value).length > 0)

const hasCliDiff = computed(() => {
  const ref = props.generatedRef
  const cur = props.configs
  if (!ref || !cur || Object.keys(ref).length === 0) return false
  return JSON.stringify(ref) !== JSON.stringify(cur)
})

const cliDiffSummary = computed(() => {
  if (!showCliDiff.value || !hasCliDiff.value) return null
  let added = 0, removed = 0, deviceCount = 0
  const ref = props.generatedRef || {}
  const cur = props.configs || {}
  for (const key of new Set([...Object.keys(ref), ...Object.keys(cur)])) {
    const diff = computeDiff(ref[key] || [], cur[key] || [])
    let hasChange = false
    for (const line of diff) {
      if (line.type === 'add') { added++; hasChange = true }
      if (line.type === 'remove') { removed++; hasChange = true }
    }
    if (hasChange) deviceCount++
  }
  return { added, removed, deviceCount }
})

function getCliDeviceDiff(deviceName) {
  const oldCmds = (props.generatedRef || {})[deviceName] || []
  const newCmds = (props.configs || {})[deviceName] || []
  return computeDiff(oldCmds, newCmds)
}

function getDeviceDiff(deviceName) {
  const oldCmds = previousConfigs.value[deviceName] || []
  const newCmds = (props.configs || {})[deviceName] || []
  return computeDiff(oldCmds, newCmds)
}

// ---- Persist configs to localStorage ----
watch(() => props.configs, (val, oldVal) => {
  if (val && Object.keys(val).length > 0) {
    try {
      // Save previous before overwriting (only if truly new generation, not initial load)
      if (oldVal && Object.keys(oldVal).length > 0 &&
          JSON.stringify(val) !== JSON.stringify(oldVal)) {
        localStorage.setItem('topo-configs-prev', JSON.stringify(oldVal))
        previousConfigs.value = JSON.parse(JSON.stringify(oldVal))
        showDiff.value = true // auto-switch to diff view on new generation
      }
      localStorage.setItem('topo-configs', JSON.stringify(val))
    } catch (_) {}
  }
}, { deep: true })

function formatDeviceName(key) {
  const match = key.match(/^(.+)_(\d+)$/)
  if (match) {
    return `${match[1]} #${match[2]}`
  }
  return key
}

function copyCommands(cmds) {
  const text = cmds.join('\n')
  navigator.clipboard.writeText(text).then(() => {
    ElMessage.success('已复制到剪贴板')
  }).catch(() => {
    ElMessage.error('复制失败，请手动复制')
  })
}

function copyAllConfigs() {
  if (!props.configs) return
  const lines = []
  for (const [dev, cmds] of Object.entries(props.configs)) {
    lines.push(`# ===== ${formatDeviceName(dev)} =====`)
    lines.push('')
    lines.push(...cmds)
    lines.push('')
  }
  const text = lines.join('\n')
  navigator.clipboard.writeText(text).then(() => {
    ElMessage.success(`已复制 ${configCount.value} 台设备配置`)
  }).catch(() => {
    ElMessage.error('复制失败，请手动复制')
  })
}

function sanitizeFilename(name) {
  return name.replace(/[<>:"/\\|?*]/g, '_').replace(/\s+/g, '_').substring(0, 64)
}

function buildConfigText() {
  const lines = []
  const now = new Date().toLocaleString('zh-CN')
  lines.push(`# 网络设备配置 — 导出时间: ${now}`)
  lines.push('')
  for (const [dev, cmds] of Object.entries(props.configs)) {
    lines.push(`# ===== ${formatDeviceName(dev)} =====`)
    lines.push(...cmds)
    lines.push('')
  }
  return lines.join('\n')
}

function downloadBlob(content, filename, type = 'text/plain;charset=utf-8') {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function handleExport(mode) {
  if (!props.configs) return

  if (mode === 'single') {
    downloadBlob(buildConfigText(), `network-configs-${Date.now()}.txt`)
    ElMessage.success('配置已导出为单个文件')
  } else if (mode === 'perdevice') {
    for (const [dev, cmds] of Object.entries(props.configs)) {
      const hostname = sanitizeFilename(formatDeviceName(dev))
      downloadBlob(cmds.join('\n'), `${hostname}.cfg`)
    }
    ElMessage.success(`已导出 ${configCount.value} 个设备配置文件`)
  } else if (mode === 'zip') {
    const zip = new JSZip()
    for (const [dev, cmds] of Object.entries(props.configs)) {
      const hostname = sanitizeFilename(formatDeviceName(dev))
      zip.file(`${hostname}.cfg`, cmds.join('\n'))
    }
    if (props.topology) {
      zip.file('topology.json', JSON.stringify(props.topology, null, 2))
    }
    const blob = await zip.generateAsync({ type: 'blob' })
    downloadBlob(blob, `network-configs-${Date.now()}.zip`, 'application/zip')
    ElMessage.success(`已导出 Zip 压缩包 (${configCount.value} 台设备)`)
  }
}
</script>

<style scoped>
.config-panel { padding: 10px; }
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.panel-actions {
  display: flex;
  gap: 8px;
}
.device-config-block {
  margin-bottom: 16px;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 10px;
  background: #fff;
}
.device-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.device-header h4 {
  margin: 0;
  font-size: 14px;
  color: #303133;
}
.code-block {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 10px;
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.6;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow-y: auto;
}
.device-count { font-size: 13px; color: #999; font-weight: normal; }
.subnet-plan { margin-bottom: 16px; }
.subnet-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 6px; margin-top: 8px; }
.subnet-item { font-size: 12px; color: #1b5e20; background: #e8f5e9; padding: 4px 8px; border-radius: 4px; }
/* Diff styles */
.diff-block code { background: transparent; display: block; }
.diff-add { background: #d4edda; color: #155724; display: block; }
.diff-remove { background: #f8d7da; color: #721c24; display: block; }
/* Version history */
.history-section { margin-top: 16px; }
.history-list { max-height: 200px; overflow-y: auto; }
.history-entry {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 10px;
  margin: 2px 0;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: background 0.15s;
}
.history-entry:hover { background: #e8f0fe; }
.history-entry.active { background: #1e88e5; color: #fff; }
.history-time { color: inherit; }
.history-count { color: inherit; font-weight: 500; }
.diff-same { display: block; color: #999; }
/* Diff summary */
.diff-summary {
  display: flex;
  gap: 12px;
  padding: 8px 12px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  margin-bottom: 12px;
  font-size: 13px;
  font-weight: 600;
}
.summary-add { color: #67C23A; }
.summary-remove { color: #F56C6C; }
.summary-devices { color: #606266; margin-left: auto; }
</style>
