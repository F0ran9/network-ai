<template>
  <div id="app-container">
    <!-- 登录门: 未认证时只渲染登录页 -->
    <LoginView v-if="!authed" @login="authed = true" />
    <template v-else>
    <el-header class="app-header">
      <div class="brand">
        <div class="brand-logo" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <rect x="2.5" y="13.5" width="19" height="7" rx="1.5"/>
            <circle cx="6.5" cy="17" r="1" fill="currentColor" stroke="none"/>
            <circle cx="10" cy="17" r="1" fill="currentColor" stroke="none"/>
            <path d="M12 13.5v-3M6 13.5V8a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v5.5M12 10.5h.01"/>
            <rect x="9" y="3" width="6" height="3" rx="1"/>
          </svg>
        </div>
        <div class="brand-text">
          <h1>网络拓扑配置生成器</h1>
          <span class="brand-sub">TOPO · CONFIG · DEPLOY</span>
        </div>
        <span class="status-led"><span class="led"></span>READY</span>
      </div>
      <div class="controls">
        <el-dropdown @command="fileMenuCmd" trigger="click">
          <el-button size="small" :icon="FolderOpened" title="保存 / 加载 / 导出图片 / 清空">
            文件<el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="save" :icon="Download">保存拓扑</el-dropdown-item>
              <el-dropdown-item command="load" :icon="Upload">加载拓扑</el-dropdown-item>
              <el-dropdown-item command="png" :icon="Camera" divided>导出图片 PNG</el-dropdown-item>
              <el-dropdown-item command="jpeg" :icon="Camera">导出图片 JPEG</el-dropdown-item>
              <el-dropdown-item command="svg" :icon="Camera">导出图片 SVG</el-dropdown-item>
              <el-dropdown-item command="clear" :icon="Delete" divided class="menu-danger">清空画布</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <input ref="fileInput" type="file" accept=".json" style="display:none" @change="onFileImport" />
        <el-button size="small" :icon="PictureFilled" @click="triggerImageImport" title="从拓扑图导入（AI 识图）">导入拓扑图</el-button>
        <el-button size="small" :icon="Connection" @click="discoverDialog?.open()" title="SSH+LLDP/CDP 扫描现网生成拓扑与诊断">网络发现</el-button>
        <input ref="imageFileInput" type="file" accept=".jpg,.jpeg,.png,.bmp,.webp" style="display:none" @change="onImageImport" />
        <el-divider direction="vertical" />
        <el-button size="small" :icon="Setting" @click="globalSettingsDialog.visible = true" title="全局设置">设置</el-button>
        <el-button size="small" :icon="Key" @click="aiConfigVisible = true" title="AI 接口配置">AI 设置</el-button>
        <el-dropdown @command="applyTemplateCmd" trigger="click">
          <el-button size="small" :icon="Files" title="从模板新建拓扑">模板<el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="tpl in topologyTemplates"
                :key="tpl.name"
                :command="tpl.name"
              >{{ tpl.icon }} {{ tpl.name }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" :icon="isDark ? Sunny : Moon" @click="toggleDarkMode" :title="isDark ? '切换日间模式' : '切换夜间模式'" />
        <el-button size="small" :loading="layoutLoading" :disabled="layoutLoading" @click="doAutoLayout" title="自动排列设备">布局</el-button>
        <el-divider direction="vertical" />
        <el-select v-model="selectedVendor" placeholder="厂商" style="width: 112px">
          <el-option v-for="v in vendors" :key="v" :label="v" :value="v" />
        </el-select>
        <el-button class="btn-accent" size="small" :loading="loading" :disabled="loading" @click="generateAllConfigs" title="按画布拓扑生成全部设备配置">
          {{ loading ? '生成中...' : '一键生成' }}
        </el-button>
        <el-button size="small" :loading="loading" :disabled="loading" @click="generateAllConfigs(true)" title="自动划分子网 / VLAN / DHCP 后生成">
          {{ loading ? '生成中...' : '自动规划生成' }}
        </el-button>
      </div>
    </el-header>
    <el-container style="flex:1; overflow:hidden;">
      <!-- eNSP-style categorized sidebar -->
      <el-aside :width="leftCollapsed ? '0px' : '240px'" class="device-sidebar" :class="{ collapsed: leftCollapsed }">
        <div class="sidebar-header">
          <el-input
            v-model="searchText"
            placeholder="搜索设备..."
            size="small"
            clearable
            :prefix-icon="Search"
          />
        </div>
        <el-collapse v-model="expandedCategories">
          <el-collapse-item
            v-for="cat in filteredCategories"
            :key="cat.name"
            :name="cat.name"
          >
            <template #title>
              <span class="category-title">{{ cat.name }}</span>
            </template>
            <div
              v-for="model in cat.models"
              :key="model.model"
              class="device-card"
              draggable="true"
              @dragstart="onDragStart($event, model)"
            >
              <DeviceIcon :type="model.type" />
              <span class="device-model">{{ model.label }}</span>
            </div>
          </el-collapse-item>
        </el-collapse>
      </el-aside>

      <!-- 左侧面板折叠手柄 -->
      <div class="panel-toggle" @click="leftCollapsed = !leftCollapsed" :title="leftCollapsed ? '展开设备面板' : '收起设备面板'">
        <el-icon :size="14"><DArrowRight v-if="leftCollapsed" /><DArrowLeft v-else /></el-icon>
      </div>

      <!-- Canvas -->
      <el-main style="padding:0;">
        <TopologyEditor
          ref="topoEditor"
          @open-cli="onOpenCli"
          @edit-device="onEditDevice"
          @export-device-config="onExportDeviceConfig"
        />
      </el-main>

      <!-- 右侧面板折叠手柄 -->
      <div class="panel-toggle" @click="rightCollapsed = !rightCollapsed" :title="rightCollapsed ? '展开配置面板' : '收起配置面板'">
        <el-icon :size="14"><DArrowLeft v-if="rightCollapsed" /><DArrowRight v-else /></el-icon>
      </div>

      <!-- Right sidebar with tabs -->
      <el-aside :width="rightCollapsed ? '0px' : '420px'" class="config-panel-aside" :class="{ collapsed: rightCollapsed }">
        <el-tabs v-model="activeTab" class="sidebar-tabs" stretch>
          <el-tab-pane label="配置" name="config">
            <div class="tab-content config-tab">
              <ConfigPanel :configs="currentConfigs" :loading="loading" :subnetPlan="subnetPlan" :generatedRef="generatedConfigsRef" :topology="currentTopology" />
            </div>
          </el-tab-pane>
          <el-tab-pane label="知识库" name="kb">
            <div class="tab-content kb-tab">
              <KnowledgePanel />
            </div>
          </el-tab-pane>
          <el-tab-pane label="AI助手" name="chat">
            <div class="tab-content chat-tab">
              <ChatPanel :topology="currentTopology" :vendor="selectedVendor" :configs="currentConfigs" />
            </div>
          </el-tab-pane>
          <el-tab-pane label="分析报告" name="analysis">
            <div class="tab-content analysis-tab">
              <AnalysisPanel
                :report="analysisResult?.analysis_report"
                :topology="analysisResult?.extracted_topology"
                :warnings="topologyWarnings"
                @apply="applyExtractedTopology"
                @focus-device="focusDevice"
              />
            </div>
          </el-tab-pane>
        </el-tabs>
      </el-aside>
    </el-container>

    <!-- Loading Overlay -->
    <LoadingOverlay :visible="analyzing" :status="analysisStatus" />

    <!-- AI 配置对话框 -->
    <AIConfigDialog v-model="aiConfigVisible" />

    <!-- 网络自动发现对话框 -->
    <NetworkDiscoverDialog ref="discoverDialog" @apply="onDiscoverApply" />

    <!-- CLI Terminal (bottom panel) -->
    <DeviceCli
      :device="cliDevice"
      :visible="cliVisible"
      @close="cliVisible = false"
      @command-executed="onCliCommandExecuted"
    />

    <!-- Device Properties Drawer -->
    <DeviceProperties
      :node-data="selectedDevice"
      @close="selectedDevice = null"
      @closed="selectedDevice = null"
      @apply="onDeviceApply"
      @delete="onDeviceDelete"
    />

    <!-- Global Settings Dialog -->
    <GlobalSettingsDialog ref="globalSettingsDialog" />
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { Search, Download, Upload, Delete, PictureFilled, Setting, Sunny, Moon, Camera, Key, FolderOpened, ArrowDown, Files, DArrowLeft, DArrowRight, Connection } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import axios from 'axios'
import TopologyEditor from './components/TopologyEditor.vue'
import ConfigPanel from './components/ConfigPanel.vue'
import ChatPanel from './components/ChatPanel.vue'
import KnowledgePanel from './components/KnowledgePanel.vue'
import AnalysisPanel from './components/AnalysisPanel.vue'
import DeviceProperties from './components/DeviceProperties.vue'
import DeviceIcon from './components/DeviceIcon.vue'
import LoadingOverlay from './components/LoadingOverlay.vue'
import DeviceCli from './components/DeviceCli.vue'
import GlobalSettingsDialog from './components/GlobalSettingsDialog.vue'
import LoginView from './components/LoginView.vue'
import AIConfigDialog from './components/AIConfigDialog.vue'
import NetworkDiscoverDialog from './components/NetworkDiscoverDialog.vue'
import { deviceCategories } from './topology/deviceDefinitions.js'
import { autoAssignSubnets } from './topology/subnetPlanner.js'
import { validateTopology } from './topology/topologyValidator.js'
import { getTemplates } from './topology/topologyTemplates.js'

const vendors = ['Huawei', 'Cisco', 'H3C', 'Ruijie', 'NSFocus', 'Sangfor', 'QiAnXin', 'Juniper', 'Arista', 'HPE', 'ZTE', 'Extreme', 'Dell', 'Sonic', 'Maipu', 'Hikvision', 'Tplink', 'Fiberhome', 'Dptecn', 'Inspur', 'Boda', 'Raisecom', 'Dcn']
const selectedVendor = ref('Huawei')
const topoEditor = ref(null)
const currentConfigs = ref({})
const currentTopology = ref({})
const loading = ref(false)
const activeTab = ref('config')
// 左右面板折叠状态
const leftCollapsed = ref(false)
const rightCollapsed = ref(false)
const selectedDevice = ref(null)
const searchText = ref('')
const fileInput = ref(null)
const imageFileInput = ref(null)
const expandedCategories = ref(deviceCategories.filter(c => c.expanded).map(c => c.name))

const subnetPlan = ref(null)  // { vlanId: { subnet, gateway, dhcpStart, dhcpEnd } }
const topologyWarnings = ref([])
const generatedConfigsRef = ref({})  // snapshot of last generated configs for diff

// Image analysis state (DeepSeek 原生视觉, 与配置生成共用同一把 key)
const analyzing = ref(false)
const analysisStatus = ref('')
const analysisResult = ref(null)  // {extracted_topology, analysis_report, configs}

// ---- 平台鉴权 / AI 设置 ----
const authed = ref(!!localStorage.getItem('tct-token'))
const aiConfigVisible = ref(false)

// CLI terminal state
const cliVisible = ref(false)
const cliDevice = ref(null)

// Global settings dialog
const globalSettingsDialog = ref(null)
const discoverDialog = ref(null)

// Auto-layout
const layoutLoading = ref(false)

async function doAutoLayout() {
  if (!topoEditor.value) {
    ElMessage.warning('拓扑编辑器未就绪')
    return
  }
  layoutLoading.value = true
  try {
    await topoEditor.value.autoLayout()
  } catch (e) {
    console.error('autoLayout error:', e)
    ElMessage.error('自动布局失败：' + (e?.message || e))
  } finally {
    layoutLoading.value = false
  }
}

// Topology templates
const topologyTemplates = getTemplates()

function applyTemplateCmd(name) {
  const tpl = topologyTemplates.find(t => t.name === name)
  if (!tpl) return
  ElMessageBox.confirm(
    `确定使用模板"${tpl.name}"？当前画布上的设备将被清空。`,
    '确认应用模板',
    { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
  ).then(() => {
    const data = tpl.generate()
    topoEditor.value?.applyTemplate(data)
    currentConfigs.value = {}
    ElMessage.success(`已应用模板：${tpl.name}`)
  }).catch(() => {})
}

// Config version history
const HISTORY_KEY = 'topo-config-history'
const MAX_HISTORY = 20

function saveConfigHistory(configs) {
  try {
    let history = []
    const raw = localStorage.getItem(HISTORY_KEY)
    if (raw) history = JSON.parse(raw)
    history.push({
      timestamp: Date.now(),
      label: new Date().toLocaleString('zh-CN'),
      deviceCount: Object.keys(configs || {}).length,
      configs: configs,
    })
    if (history.length > MAX_HISTORY) history = history.slice(-MAX_HISTORY)
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history))
  } catch (_) {}
}

function getConfigHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    return raw ? JSON.parse(raw) : []
  } catch (_) { return [] }
}

// Dark mode
const isDark = ref(document.documentElement.classList.contains('dark'))

function toggleDarkMode() {
  isDark.value = !isDark.value
  if (isDark.value) {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
  localStorage.setItem('topo-dark-mode', isDark.value.toString())
}

// Sync selected device from TopologyEditor
watch(() => topoEditor.value?.selectedNodeData, (data) => {
  selectedDevice.value = data || null
})

// Handlers for DeviceProperties
function onDeviceApply({ key, ...props }) {
  topoEditor.value?.updateNodeData(key, props)
  selectedDevice.value = null
}

function onDeviceDelete(key) {
  topoEditor.value?.deleteNode(key)
  selectedDevice.value = null
}

// ---- CLI handlers ----
function onOpenCli(device) {
  cliDevice.value = {
    key: device.key,
    label: device.label || device.key,
    hostname: device.hostname || device.label || device.key,
    vendor: device.vendor || selectedVendor.value,
    category: device.category || 'switch',
  }
  cliVisible.value = true
}

function onEditDevice(device) {
  selectedDevice.value = device
}

function onExportDeviceConfig(device) {
  if (!device?.key) return
  const config = currentConfigs.value[device.key]
  if (!config || config.length === 0) {
    ElMessage.warning('该设备暂无配置，请先生成配置')
    return
  }
  const text = Array.isArray(config) ? config.join('\n') : String(config)
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${device.label || device.key}_config.txt`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('配置已导出')
}

function onCliCommandExecuted({ deviceKey, runningConfig }) {
  if (!deviceKey || !runningConfig) return
  currentConfigs.value[deviceKey] = runningConfig
  try { localStorage.setItem('topo-configs', JSON.stringify(currentConfigs.value)) } catch (_) {}
}

// Restore saved configs from last session
onMounted(() => {
  try {
    const saved = localStorage.getItem('topo-configs')
    if (saved) {
      currentConfigs.value = JSON.parse(saved)
    }
  } catch (_) {}
})

// ---- Topology import/export/clear ----
function triggerImport() {
  fileInput.value?.click()
}

function exportImage(format) {
  topoEditor.value?.exportToImage(format)
}

// 文件下拉菜单: 保存 / 加载 / 导出图片 / 清空
function fileMenuCmd(cmd) {
  if (cmd === 'save') topoEditor.value?.exportTopologyFile()
  else if (cmd === 'load') triggerImport()
  else if (cmd === 'clear') confirmClear()
  else if (['png', 'jpeg', 'svg'].includes(cmd)) exportImage(cmd)
}

function onFileImport(ev) {
  const file = ev.target.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    topoEditor.value?.importTopologyFile(reader.result)
  }
  reader.readAsText(file)
  // Reset so the same file can be re-imported
  ev.target.value = ''
}

// ---- Image topology import (DeepSeek 原生视觉) ----
function triggerImageImport() {
  imageFileInput.value?.click()
}

async function onImageImport(ev) {
  const file = ev.target.files?.[0]
  if (!file) return

  const allowed = ['image/jpeg', 'image/png', 'image/bmp', 'image/webp']
  if (!allowed.includes(file.type)) {
    ElMessage.error('仅支持 JPG、PNG、BMP、WebP 格式的图片')
    return
  }
  if (file.size > 20 * 1024 * 1024) {
    ElMessage.error('图片大小不能超过 20MB')
    return
  }

  analyzing.value = true
  analysisStatus.value = '正在上传图片...'

  try {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('vendor', selectedVendor.value)
    formData.append('generate_configs', 'true')

    analysisStatus.value = 'DeepSeek 正在识别拓扑结构（约需 30-60 秒）...'
    const res = await axios.post('/api/analyze/topology-image', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 360000,
    })

    if (res.data.status === 'success') {
      analysisResult.value = {
        extracted_topology: res.data.extracted_topology,
        analysis_report: res.data.analysis_report,
        configs: res.data.configs || {},
      }
      analysisStatus.value = '正在绘制拓扑图...'
      topoEditor.value?.importTopologyFromAnalysis(res.data.extracted_topology)

      currentTopology.value = res.data.extracted_topology
      currentConfigs.value = res.data.configs || {}
      try { localStorage.setItem('topo-configs', JSON.stringify(res.data.configs || {})) } catch (_) {}

      activeTab.value = 'analysis'

      if (res.data.warnings?.length) {
        ElMessage.warning('分析完成，但有 ' + res.data.warnings.length + ' 条警告')
      } else {
        ElMessage.success('拓扑图分析完成！已自动生成配置')
      }
    }
  } catch (err) {
    const detail = err.response?.data?.detail || err.message
    ElMessage.error('分析失败：' + detail)
    console.error('Image analysis error:', err)
  } finally {
    analyzing.value = false
    analysisStatus.value = ''
    ev.target.value = ''
  }
}

function applyExtractedTopology() {
  if (analysisResult.value?.extracted_topology) {
    topoEditor.value?.importTopologyFromAnalysis(analysisResult.value.extracted_topology)
    currentTopology.value = analysisResult.value.extracted_topology
    activeTab.value = 'config'
    ElMessage.success('拓扑已应用到画布，可在画布上编辑调整')
  }
}

// 网络自动发现: 应用扫描出的拓扑到画布
function onDiscoverApply(topology) {
  if (!topology?.nodes) return
  topoEditor.value?.importTopologyFromAnalysis(topology)
  currentTopology.value = topology
  activeTab.value = 'config'
}

function focusDevice(deviceKey) {
  topoEditor.value?.focusDevice(deviceKey)
  activeTab.value = 'editor'
}

function confirmClear() {
  ElMessageBox.confirm(
    '确定清空画布上所有设备和连线？此操作不可恢复。',
    '确认清空',
    { confirmButtonText: '清空', cancelButtonText: '取消', type: 'warning' }
  ).then(() => {
    topoEditor.value?.clearTopology()
    currentConfigs.value = {}
    currentTopology.value = {}
  }).catch(() => {})
}

const filteredCategories = computed(() => {
  const models = deviceCategories.map(cat => {
    let filtered = cat.models
    // Filter by search text
    if (searchText.value) {
      const q = searchText.value.toLowerCase()
      filtered = filtered.filter(m =>
        m.model.toLowerCase().includes(q) || m.label.toLowerCase().includes(q)
      )
    }
    // Filter by selected vendor (通用 always shows)
    if (selectedVendor.value) {
      filtered = filtered.filter(m =>
        !m.vendor || m.vendor === 'Generic' || m.vendor === selectedVendor.value
      )
    }
    return { ...cat, models: filtered }
  }).filter(cat => cat.models.length > 0)
  return models
})

function onDragStart(ev, dev) {
  ev.dataTransfer.setData('application/json', JSON.stringify(dev))
}

async function generateAllConfigs(autoPlanSubnets = false) {
  if (!topoEditor.value) {
    ElMessage.warning('拓扑编辑器未就绪')
    return
  }
  const topoData = topoEditor.value.getTopologyData()
  if (!topoData || !topoData.nodes || Object.keys(topoData.nodes).length === 0) {
    ElMessage.warning('请先绘制拓扑图（拖入设备并连线）')
    return
  }

  loading.value = true
  try {
    currentTopology.value = topoData

    // Run topology validation
    topologyWarnings.value = validateTopology(topoData)

    // Auto-plan subnets if requested
    if (autoPlanSubnets) {
      const allVlans = new Set()
      for (const link of (topoData.links || [])) {
        if (link.accessVlan) allVlans.add(link.accessVlan)
        for (const v of (link.allowedVlans || [])) {
          const vi = typeof v === 'string' ? parseInt(v, 10) : v
          if (!isNaN(vi)) allVlans.add(vi)
        }
      }
      subnetPlan.value = autoAssignSubnets([...allVlans])
      topoData.subnetPlan = subnetPlan.value
    }

    if (topologyWarnings.value.length > 0) {
      activeTab.value = 'analysis'
    }

    const gs = globalSettingsDialog.value?.getSettings()
    const res = await axios.post('/api/generate', {
      topology: topoData,
      vendor: selectedVendor.value,
      globalSettings: gs
    })
    currentConfigs.value = res.data.config
    generatedConfigsRef.value = JSON.parse(JSON.stringify(res.data.config))
    const count = Object.keys(res.data.config || {}).length
    saveConfigHistory(res.data.config)
    ElMessage.success(`配置生成完成，共 ${count} 台设备`)
    activeTab.value = 'config'
  } catch (err) {
    ElMessage.error('生成失败：' + (err.response?.data?.detail || err.message))
  } finally {
    loading.value = false
  }
}
</script>

<style>
html, body { margin: 0; padding: 0; height: 100%; }
#app { height: 100%; }
#app-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--tct-bg);
}

/* ============ 机柜头部：恒定深色，双主题下的记忆点 ============ */
.app-header {
  background: var(--tct-rack-bg);
  padding: 0 20px;
  height: 56px !important;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
  border-bottom: 1px solid var(--tct-rack-line);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
  position: relative;
  z-index: 5;
}
/* 顶部的"面板螺丝"细节：四角定位孔 */
.app-header::before,
.app-header::after {
  content: "";
  position: absolute;
  top: 50%;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: rgba(148, 187, 208, 0.22);
  transform: translateY(-50%);
}
.app-header::before { left: 8px; }
.app-header::after { right: 8px; }

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.brand-logo {
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  color: var(--tct-accent);
  background: rgba(240, 167, 46, 0.10);
  border: 1px solid rgba(240, 167, 46, 0.28);
  border-radius: var(--tct-radius);
}
.brand-text { display: flex; flex-direction: column; line-height: 1.25; min-width: 0; }
.brand-text h1 {
  margin: 0;
  font-family: var(--tct-mono);
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--tct-rack-ink);
  white-space: nowrap;
}
.brand-sub {
  font-family: var(--tct-mono);
  font-size: 10px;
  letter-spacing: 0.22em;
  color: var(--tct-rack-muted);
  white-space: nowrap;
}

/* 运行状态灯：呼吸绿点， industrial 状态语义 */
.status-led {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: 14px;
  padding: 3px 10px;
  border: 1px solid var(--tct-rack-line);
  border-radius: 999px;
  font-family: var(--tct-mono);
  font-size: 10px;
  letter-spacing: 0.14em;
  color: var(--tct-rack-muted);
  white-space: nowrap;
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
}
@keyframes led-breathe {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.45; }
}

/* ============ 控制区：强制单行, 窄屏收副标题 ============ */
.controls {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: nowrap;
  justify-content: flex-end;
  min-width: 0;
}
.controls .el-button { flex-shrink: 0; }
@media (max-width: 1660px) {
  .brand-sub, .status-led { display: none; }
}
@media (max-width: 1360px) {
  .brand-text h1 { font-size: 13px; }
  .brand-logo { display: none; }
}
/* 控件分组发丝分隔线 */
.controls .el-divider--vertical {
  height: 20px;
  border-color: rgba(148, 187, 208, 0.22);
  margin: 0 2px;
}
/* 下拉菜单危险项（清空画布） */
.menu-danger { color: var(--tct-danger); }
/* 深色头部里的次级按钮统一"暗面板键"质感 */
.app-header .el-button:not(.el-button--primary):not(.el-button--warning):not(.el-button--danger):not(.el-button--success) {
  background: rgba(148, 187, 208, 0.07);
  border-color: rgba(148, 187, 208, 0.24);
  color: var(--tct-rack-ink);
}
.app-header .el-button:not(.el-button--primary):not(.el-button--warning):not(.el-button--danger):not(.el-button--success):hover {
  background: rgba(148, 187, 208, 0.16);
  border-color: rgba(148, 187, 208, 0.4);
}
/* 头部厂商选择器融入机柜面板 */
.app-header .el-select {
  --el-fill-color-blank: rgba(148, 187, 208, 0.07);
}
.app-header .el-select .el-select__wrapper {
  background: rgba(148, 187, 208, 0.07);
  box-shadow: 0 0 0 1px rgba(148, 187, 208, 0.24) inset;
  color: var(--tct-rack-ink);
  min-height: 26px;
}
/* 兼容旧版 el-select（基于 el-input 的渲染结构） */
.app-header .el-select .el-input__wrapper {
  background: rgba(148, 187, 208, 0.07);
  box-shadow: 0 0 0 1px rgba(148, 187, 208, 0.24) inset;
  color: var(--tct-rack-ink);
}
.app-header .el-select .el-input__inner { color: var(--tct-rack-ink); }
.app-header .el-select .el-select__wrapper.is-hovering,
.app-header .el-select .el-select__wrapper.is-focused {
  box-shadow: 0 0 0 1px var(--tct-brand) inset;
}
.app-header .el-select .el-select__placeholder { color: var(--tct-rack-muted); }

/* 琥珀强调：只给"一键生成"这一个关键动作 */
.btn-accent {
  --el-button-bg-color: var(--tct-accent);
  --el-button-border-color: var(--tct-accent);
  --el-button-hover-bg-color: var(--tct-accent-strong);
  --el-button-hover-border-color: var(--tct-accent-strong);
  --el-button-active-bg-color: var(--tct-accent-strong);
  color: #17130a !important;
  font-weight: 700;
}
</style>

<style scoped>
/* ============ 左侧设备栏 ============ */
.device-sidebar {
  background: var(--tct-surface);
  overflow-y: auto;
  border-right: 1px solid var(--tct-border);
  transition: width .25s ease;
}
.device-sidebar.collapsed {
  overflow: hidden;
  border-right: none;
  min-width: 0;
}
/* 左右面板折叠手柄 (贴在画布两侧的细条) */
.panel-toggle {
  width: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--tct-text-secondary, #909399);
  background: var(--tct-panel);
  border-right: 1px solid var(--tct-border);
  transition: background .2s, color .2s;
  flex-shrink: 0;
}
.panel-toggle:last-of-type {
  border-right: none;
  border-left: 1px solid var(--tct-border);
}
.panel-toggle:hover {
  background: var(--tct-surface);
  color: var(--el-color-primary);
}
.sidebar-header {
  padding: 10px;
  border-bottom: 1px solid var(--tct-border);
  background: var(--tct-panel);
  position: sticky;
  top: 0;
  z-index: 2;
}
.category-title {
  font-family: var(--tct-mono);
  font-weight: 600;
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--tct-muted);
}
/* 设备卡：发丝边框 + 悬停左侧琥珀指示条 */
.device-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px 6px 12px;
  margin: 2px 6px;
  cursor: grab;
  user-select: none;
  border: 1px solid transparent;
  border-left: 2px solid transparent;
  border-radius: var(--tct-radius);
  transition: background var(--tct-dur-fast) ease-out,
              border-color var(--tct-dur-fast) ease-out,
              transform var(--tct-dur-fast) ease-out;
}
.device-card:hover {
  background: var(--tct-brand-soft);
  border-color: var(--tct-border);
  border-left-color: var(--tct-accent);
  transform: translateX(2px);
}
.device-card:active {
  cursor: grabbing;
  background: var(--tct-brand-soft);
  transform: translateX(2px) scale(0.99);
}
.device-model {
  font-size: var(--tct-fs-sm);
  color: var(--tct-ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-variant-numeric: tabular-nums;
}

/* ============ 右侧面板 ============ */
.config-panel-aside {
  background: var(--tct-panel);
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--tct-border);
  overflow: hidden;
  transition: width .25s ease;
}
.config-panel-aside.collapsed {
  border-left: none;
  min-width: 0;
}
.sidebar-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.sidebar-tabs :deep(.el-tabs__header) {
  margin: 0;
  flex-shrink: 0;
  background: var(--tct-surface);
  border-bottom: 1px solid var(--tct-border);
  padding: 0 8px;
}
/* 页签文字用等宽小字距，工业标签牌质感 */
.sidebar-tabs :deep(.el-tabs__item) {
  font-family: var(--tct-mono);
  font-size: var(--tct-fs-sm);
  letter-spacing: 0.06em;
  color: var(--tct-muted);
  height: 40px;
  line-height: 40px;
}
.sidebar-tabs :deep(.el-tabs__item.is-active) {
  color: var(--tct-brand);
  font-weight: 700;
}
.sidebar-tabs :deep(.el-tabs__active-bar) {
  height: 2px;
}
.sidebar-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow: hidden;
  background: var(--tct-panel);
}
.sidebar-tabs :deep(.el-tab-pane) {
  height: 100%;
  overflow: hidden;
}
.tab-content {
  height: 100%;
  overflow-y: auto;
  padding: 8px 10px;
}
.config-tab, .kb-tab, .chat-tab, .analysis-tab { padding: 0; }
</style>
