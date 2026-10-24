<template>
  <div class="canvas-wrap">
    <div
      id="topologyCanvas"
      ref="canvasRef"
      style="width:100%; height:100%; outline:none;"
      @dragenter.prevent
      @dragover.prevent
      @drop.prevent="onDrop"
      @keydown="onKeyDown"
      @contextmenu.prevent="onContextMenu"
      tabindex="0"
    ></div>

    <!-- 图例 (eNSP 风格) -->
    <div class="canvas-legend" :class="{ collapsed: !legendOpen }">
      <div class="legend-header" @click="legendOpen = !legendOpen">
        <span class="legend-title">图 例</span>
        <span class="legend-toggle">{{ legendOpen ? '▾' : '▸' }}</span>
      </div>
      <div v-show="legendOpen" class="legend-grid">
        <div class="legend-item" v-for="it in legendItems" :key="it.name">
          <img v-if="it.img" :src="it.img" class="legend-img">
          <span v-else class="legend-icon" v-html="it.svg"></span>
          <span class="legend-name">{{ it.name }}</span>
        </div>
      </div>
    </div>
  </div>

  <!-- Right-click context menu -->
  <teleport to="body">
    <div
      v-if="ctxMenu.visible"
      class="canvas-context-menu"
      :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }"
      @click.stop
    >
      <div
        v-for="(item, i) in ctxMenu.items"
        :key="i"
        class="ctx-menu-item"
        :class="{ 'ctx-menu-divider': item.divider, 'ctx-menu-danger': item.danger }"
        @click="handleContextAction(item.action)"
      >
        <el-icon v-if="item.icon" style="margin-right:6px"><component :is="item.icon" /></el-icon>
        <span>{{ item.label }}</span>
        <span v-if="item.shortcut" class="ctx-shortcut">{{ item.shortcut }}</span>
      </div>
    </div>
  </teleport>

  <!-- Link VLAN config dialog -->
  <LinkConfigDialog
    v-model="showLinkDialog"
    :from-label="linkFromLabel"
    :to-label="linkToLabel"
    :mode="linkMode"
    :access-vlan="linkAccessVlan"
    :allowed-vlans="linkAllowedVlans"
    :native-vlan="linkNativeVlan"
    :from-ports="linkFromPorts"
    :to-ports="linkToPorts"
    :from-port="linkFromPort"
    :to-port="linkToPort"
    :is-bonded="isBonded"
    :eth-trunk-id="ethTrunkId"
    :member-ports-from="memberPortsFrom"
    :member-ports-to="memberPortsTo"
    :lacp-mode="lacpMode"
    :load-balance="loadBalance"
    :link-bandwidth="linkBandwidth"
    @confirm="onLinkConfigConfirm"
  />
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref, nextTick } from 'vue'
import go from 'gojs'
import { ElMessage } from 'element-plus'
import { Monitor, Edit, CopyDocument, Download, Delete, Link, FullScreen, Camera } from '@element-plus/icons-vue'
import { createGridPattern } from '../topology/gridPattern.js'
import { createNodeTemplateMap, PORT_SPECS } from '../topology/nodeTemplateFactory.js'
import { getLinkProperties } from '../topology/connectionRules.js'
import LinkConfigDialog from './LinkConfigDialog.vue'

const $ = go.GraphObject.make
const canvasRef = ref(null)
let diagram = null
const modelCounters = {}
const TOPO_STORAGE_KEY = 'topo-model'
let saveTimer = null

// ---- Context menu state ----
const ctxMenu = ref({ visible: false, x: 0, y: 0, items: [], targetType: null, targetData: null })
let ctxMenuTargetPart = null
let copiedNodeData = null  // For copy/paste device

const emit = defineEmits(['open-cli', 'edit-device', 'export-device-config'])

// ---- 图例数据 (NetEquip 实物图 + AI 生成实物图 + 矢量图标混合) ----
import routerImg from '../assets/netequip/icons/router.png'
import switchImg from '../assets/netequip/icons/switch-core.png'
import firewallImg from '../assets/netequip/icons/firewall.png'
import apImg from '../assets/netequip/icons/ap.png'
import serverImg from '../assets/netequip/icons/server.png'
import lbImg from '../assets/netequip/icons/lb.png'
import sdwanImg from '../assets/netequip/icons/sdwan.png'
import behaviorImg from '../assets/netequip/icons/behavior.png'
const legendOpen = ref(true)
const legendItems = [
  { name: '路由器', img: routerImg },
  { name: '交换机', img: switchImg },
  { name: '防火墙', img: firewallImg },
  { name: '负载均衡', img: lbImg },
  { name: 'SDWAN路由器', img: sdwanImg },
  { name: '上网行为管理', img: behaviorImg },
  { name: '运营商/外网', svg: '<svg width="38" height="26" viewBox="0 0 38 26"><path d="M10 20 a6 6 0 0 1 -1 -11.9 A8 8 0 0 1 24 5.5 A6.5 6.5 0 0 1 30 20 Z" fill="#E3F2FD" stroke="#1565C0" stroke-width="1.5"/></svg>' },
  { name: '无线控制器', svg: '<svg width="34" height="26" viewBox="0 0 34 26"><rect x="3" y="6" width="28" height="15" rx="2" fill="#7E57C2" stroke="#4A148C"/><rect x="8" y="10" width="18" height="2" fill="#fff" opacity=".85"/><rect x="8" y="14" width="12" height="2" fill="#fff" opacity=".85"/></svg>' },
  { name: '无线AP', img: apImg },
  { name: '服务器', img: serverImg },
  { name: '终端/PC', svg: '<svg width="30" height="26" viewBox="0 0 30 26"><rect x="4" y="3" width="22" height="15" rx="2" fill="#263238"/><rect x="7" y="6" width="16" height="9" fill="#1565C0"/><rect x="13" y="18" width="4" height="4" fill="#37474F"/><rect x="8" y="22" width="14" height="2.4" fill="#37474F"/></svg>' },
]

// ---- Link dialog state ----
const showLinkDialog = ref(false)
const linkFromLabel = ref('')
const linkToLabel = ref('')
const linkMode = ref('access')
const linkAccessVlan = ref(10)
const linkAllowedVlans = ref(['10', '20'])
const linkNativeVlan = ref(1)
const linkFromPort = ref('')
const linkToPort = ref('')
const linkFromPorts = ref([])
const linkToPorts = ref([])
let currentLinkKey = null  // track which link is being edited
// Eth-Trunk link state
const ethTrunkId = ref(null)
const memberPortsFrom = ref([])
const memberPortsTo = ref([])
const lacpMode = ref('static')
const loadBalance = ref('src-dst-ip')
const isBonded = ref(false)
const linkBandwidth = ref('10GE')

// ---- Node selection state ----
const selectedNodeData = ref(null)

function updateNodeData(key, props) {
  if (!diagram) return
  const node = diagram.model.findNodeDataForKey(key)
  if (!node) return
  for (const [k, v] of Object.entries(props)) {
    diagram.model.setDataProperty(node, k, v)
  }
  // If label changed, update node label (which is bound to 'label')
  if (props.label) {
    diagram.model.setDataProperty(node, 'label', props.label)
  }
  // Update selectedNodeData reactively
  const updated = diagram.model.findNodeDataForKey(key)
  if (updated && selectedNodeData.value?.key === key) {
    selectedNodeData.value = { ...updated }
  }
}

function deleteNode(key) {
  if (!diagram) return
  diagram.select(diagram.findNodeForKey(key))
  diagram.commandHandler.deleteSelection()
  selectedNodeData.value = null
}

// ---- Drop handler ----
function onDrop(ev) {
  if (!diagram) return
  try {
    const data = JSON.parse(ev.dataTransfer.getData('application/json'))
    const rect = canvasRef.value.getBoundingClientRect()
    const x = ev.clientX - rect.left
    const y = ev.clientY - rect.top
    const canvasPoint = diagram.transformViewToDoc(new go.Point(x, y))
    if (!modelCounters[data.model]) modelCounters[data.model] = 0
    modelCounters[data.model]++
    const key = `${data.model}_${modelCounters[data.model]}`
    diagram.model.addNodeData({
      key: key,
      category: normalizeCategory(data.type),
      label: data.label || data.model,
      role: data.role,
      model: data.model,
      vendor: data.vendor || 'Huawei',
      hostname: data.hostname || data.model,
      vlan: data.vlan || null,
      description: data.description || '',
      loc: go.Point.stringify(canvasPoint),
    })
  } catch (_) { /* ignore invalid drops */ }
}

function onKeyDown(ev) {
  if (!diagram) return
  if (ev.key === 'Delete' || ev.key === 'Backspace') {
    ev.preventDefault()
    diagram.commandHandler.deleteSelection()
  }
}

// ---- Link config dialog ----
function openLinkConfig(linkData) {
  const model = diagram.model
  const fromNode = model.findNodeDataForKey(linkData.from)
  const toNode = model.findNodeDataForKey(linkData.to)
  const props = fromNode && toNode ? getLinkProperties(fromNode, toNode) : { label: 'Link' }
  linkFromLabel.value = fromNode?.label || linkData.from
  linkToLabel.value = toNode?.label || linkData.to
  linkMode.value = props.label === 'Eth-Trunk' ? 'trunk' : linkData.linkMode || (props.label === 'Trunk' ? 'trunk' : 'access')
  linkAccessVlan.value = linkData.accessVlan || 10
  linkAllowedVlans.value = linkData.allowedVlans || ['10', '20']
  linkNativeVlan.value = linkData.nativeVlan || 1

  // Look up available ports for both devices
  const fromCat = fromNode?.category || 'pc'
  const toCat = toNode?.category || 'pc'
  const fromSpec = PORT_SPECS[fromCat] || PORT_SPECS.pc
  const toSpec = PORT_SPECS[toCat] || PORT_SPECS.pc
  linkFromPorts.value = [...fromSpec.names]
  linkToPorts.value = [...toSpec.names]
  linkFromPort.value = linkData.fromPort || fromSpec.names[0] || ''
  linkToPort.value = linkData.toPort || toSpec.names[0] || ''

  // Eth-Trunk fields
  ethTrunkId.value = linkData.ethTrunkId || null
  memberPortsFrom.value = linkData.memberPortsFrom || []
  memberPortsTo.value = linkData.memberPortsTo || []
  lacpMode.value = linkData.lacpMode || 'static'
  loadBalance.value = linkData.loadBalance || 'src-dst-ip'
  isBonded.value = linkData.bonded || props.bonded || false
  linkBandwidth.value = linkData.bandwidth || props.bandwidth || '10GE'

  currentLinkKey = linkData.__gohashid || linkData.key
  showLinkDialog.value = true
}

function onLinkConfigConfirm(config) {
  if (currentLinkKey === null || !diagram) return
  const model = diagram.model
  // Find the link by matching data in the linkDataArray
  const link = model.linkDataArray.find(l =>
    (l.__gohashid === currentLinkKey) || (l.key === currentLinkKey)
  )
  if (!link) {
    // Try to find the most recently added link
    const lastLink = model.linkDataArray[model.linkDataArray.length - 1]
    if (lastLink) {
      applyVlanConfig(lastLink, config)
    }
    return
  }
  applyVlanConfig(link, config)
  currentLinkKey = null
}

function applyVlanConfig(link, config) {
  const model = diagram.model
  model.setDataProperty(link, 'fromPort', config.fromPort)
  model.setDataProperty(link, 'toPort', config.toPort)
  model.setDataProperty(link, 'accessVlan', config.accessVlan)
  model.setDataProperty(link, 'allowedVlans', config.allowedVlans)
  model.setDataProperty(link, 'nativeVlan', config.nativeVlan)

  // Eth-Trunk fields
  if (config.ethTrunkId != null) {
    model.setDataProperty(link, 'ethTrunkId', config.ethTrunkId)
    model.setDataProperty(link, 'memberPortsFrom', config.memberPortsFrom || [])
    model.setDataProperty(link, 'memberPortsTo', config.memberPortsTo || [])
    model.setDataProperty(link, 'lacpMode', config.lacpMode || 'static')
    model.setDataProperty(link, 'loadBalance', config.loadBalance || 'src-dst-ip')
    model.setDataProperty(link, 'bonded', true)
    model.setDataProperty(link, 'linkStrokeWidth', 4)
  }

  // Build label
  const bonded = config.ethTrunkId != null
  const bw = config.bandwidth || link.bandwidth || '10GE'
  let portPart
  if (bonded && config.memberPortsFrom?.length > 0 && config.memberPortsTo?.length > 0) {
    const fromPorts = config.memberPortsFrom.map(p => p.replace('GigabitEthernet', 'GE').replace('Ethernet', 'Eth')).join(',')
    const toPorts = config.memberPortsTo.map(p => p.replace('GigabitEthernet', 'GE').replace('Ethernet', 'Eth')).join(',')
    portPart = `Eth-Trunk${config.ethTrunkId} (${bw}): [${fromPorts}] ↔ [${toPorts}]`
  } else {
    portPart = `${config.fromPort || '?'} → ${config.toPort || '?'}`
  }
  const vlanPart = linkMode.value === 'trunk'
    ? `Trunk VLAN [${(config.allowedVlans || []).join(',')}]`
    : `Access VLAN ${config.accessVlan}`
  model.setDataProperty(link, 'linkLabel', `${portPart}  |  ${vlanPart}`)
  model.setDataProperty(link, 'vlanConfigured', true)
  model.setDataProperty(link, 'bandwidth', bw)
}

// ---- Export topology data ----
function getTopologyData() {
  if (!diagram) return { nodes: {}, links: [] }
  const model = diagram.model
  const nodes = {}
  model.nodeDataArray.forEach(n => {
    if (n.category === 'zone') return // 安全域分区框不是设备, 不参与配置生成
    const roleDesc = n.role === 'core' ? '核心交换机'
      : n.role === 'access' ? '接入交换机'
      : n.role === 'router' ? '路由器'
      : n.role === 'security' ? '防火墙'
      : n.role === 'endpoint' ? '终端'
      : n.role
    nodes[n.key] = {
      key: n.key,
      label: n.label,
      model: n.model,
      role: n.role,
      category: n.category,
      description: `${n.model || n.label} (${roleDesc})`,
      vendor: n.vendor || 'Huawei',
    }
  })
  const links = model.linkDataArray.map(l => ({
    from: l.from,
    to: l.to,
    fromPort: l.fromPort || '',
    toPort: l.toPort || '',
    linkLabel: l.linkLabel || '',
    mode: l.linkLabel && l.linkLabel.startsWith('Trunk') ? 'trunk' : 'access',
    accessVlan: l.accessVlan || null,
    allowedVlans: l.allowedVlans || [],
    nativeVlan: l.nativeVlan || 1,
    bonded: l.bonded || false,
    ethTrunkId: l.ethTrunkId || null,
    memberPortsFrom: l.memberPortsFrom || [],
    memberPortsTo: l.memberPortsTo || [],
    lacpMode: l.lacpMode || 'static',
    loadBalance: l.loadBalance || 'src-dst-ip',
    bandwidth: l.bandwidth || '10GE',
  }))
  return { nodes, links }
}

function exportTopologyFile() {
  if (!diagram) return
  const json = diagram.model.toJson()
  const blob = new Blob([json], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `topology-${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
}

function importTopologyFile(jsonString) {
  if (!diagram) return
  try {
    const json = JSON.parse(jsonString)
    // Validate: must have nodeDataArray or be a valid GoJS model
    if (!json.nodeDataArray && !json.linkDataArray && !json.class) {
      throw new Error('Invalid topology file')
    }
    const restored = go.Model.fromJson(JSON.stringify(json))
    if (restored instanceof go.GraphLinksModel) restored.nodeLayerKeyProperty = 'layerName'
    // 净化 category，防止外部文件里的旧值导致节点回退成纯文字
    restored.nodeDataArray.forEach(n => {
      const fixed = normalizeCategory(n.category)
      if (fixed !== n.category) n.category = fixed
    })
    diagram.model = restored
    // Rebuild modelCounters from loaded nodes
    for (const k of Object.keys(modelCounters)) delete modelCounters[k]
    diagram.model.nodeDataArray.forEach(n => {
      const match = n.key?.match(/^(.+)_(\d+)$/)
      if (match && !n.key.startsWith('__')) { // 跳过 __zone_* 等内部节点
        const base = match[1]
        const num = parseInt(match[2], 10)
        if (!modelCounters[base] || modelCounters[base] < num) {
          modelCounters[base] = num
        }
      }
    })
    saveModel()
  } catch (e) {
    alert('拓扑文件格式无效：' + e.message)
  }
}

function clearTopology() {
  if (!diagram) return
  diagram.model = new go.GraphLinksModel({
    nodeDataArray: [],
    linkDataArray: [],
    nodeCategoryProperty: 'category',
    nodeLayerKeyProperty: 'layerName',
  })
  for (const k of Object.keys(modelCounters)) delete modelCounters[k]
  localStorage.removeItem(TOPO_STORAGE_KEY)
  localStorage.removeItem('topo-counters')
  selectedNodeData.value = null
}

// 把任意历史/外部 category 值净化为模板表里存在的键，防止回退成纯文字节点
const VALID_CATEGORIES = new Set([
  'router', 'switch', 'pc', 'laptop', 'server', 'firewall', 'ips',
  'camera', 'nvr', 'dumb-switch', 'printer', 'ap', 'ac', 'phone', 'cloud',
  'zone', 'lb', 'sdwan', 'behavior',
])
function normalizeCategory(cat) {
  const c = String(cat || '').toLowerCase().trim()
  if (VALID_CATEGORIES.has(c)) return c
  const alias = {
    terminal: 'pc', other: 'pc', host: 'pc', endpoint: 'pc', computer: 'pc',
    wireless: 'ap', wifi: 'ap', ap: 'ap',
    firewall: 'firewall', fw: 'firewall', security: 'firewall',
    router: 'router', gateway: 'router',
    switch: 'switch', sw: 'switch',
    server: 'server', camera: 'camera', nvr: 'nvr', ac: 'ac', cloud: 'cloud',
    l3switch: 'switch', 'core-switch': 'switch', 'access-switch': 'switch',
    lb: 'lb', loadbalancer: 'lb', 'load-balancer': 'lb', arrays: 'lb',
    sdwan: 'sdwan', wan: 'sdwan',
    behavior: 'behavior', 'behavior-management': 'behavior', bm: 'behavior',
  }
  return alias[c] || 'pc'
}

// 链路属性自动标注: 仅在 AI 明确给出 mode 时生成 (忠实原图, 判断不了不标)
function autoLinkLabel(link) {
  const mode = String(link.mode || '').toLowerCase()
  let base = ''
  if (mode === 'trunk') base = 'Trunk'
  else if (['l3', 'routed', 'layer3', '三层', '三层互联'].includes(mode)) base = '三层互联'
  else if (mode === 'access') base = 'Access'
  // mode 为 unknown/空时: 原图没标注链路属性, 不编造, 只透出原图给的带宽
  const parts = base ? [base] : []
  if (link.bandwidth) parts.push(link.bandwidth)
  if (link.redundancy === 'backup') parts.push('（备）')
  return parts.join(' · ')
}

// 安全域分区框: 仅当 AI 提取到原图的分组框 (zones) 时才画, 名称照抄原图, 不脑补
function buildZoneNodes(topoData, positions) {
  const zones = Array.isArray(topoData.zones) ? topoData.zones : []
  const result = []
  const PAD_X = 48
  const PAD_TOP = 62
  const PAD_BOTTOM = 148
  zones.forEach((z, i) => {
    const members = (z.members || []).filter(k => positions.has(k))
    if (!members.length) return
    let minX = Infinity, maxX = -Infinity, y = 0
    for (const k of members) {
      const p = positions.get(k)
      if (p.x - 90 < minX) minX = p.x - 90   // 90 ≈ 节点半宽
      if (p.x + 90 > maxX) maxX = p.x + 90
      y = Math.max(y, p.y)
    }
    result.push({
      key: `__zone_${i}_${z.name || 'area'}`,
      category: 'zone',
      label: z.name || '业务分区',
      loc: go.Point.stringify(new go.Point(minX - PAD_X, y - PAD_TOP)),
      size: go.Size.stringify(new go.Size((maxX - minX) + PAD_X * 2, PAD_TOP + PAD_BOTTOM)),
      layerName: 'Background',
    })
  })
  return result
}

function importTopologyFromAnalysis(topoData) {
  if (!diagram) return
  try {
    const nodes = topoData.nodes || {}
    const links = topoData.links || []

    // Compute layout positions based on zone and role
    const { positions } = _computeLayout(topoData)

    // Build nodeDataArray
    const nodeDataArray = []
    for (const [key, node] of Object.entries(nodes)) {
      const pos = positions.get(key) || { x: Math.random() * 400 + 100, y: Math.random() * 300 + 100 }
      // Map category to GoJS template name (device type)
      const cat = node.category || 'terminal'
      const lbl = (node.label || node.hostname || key || '').toLowerCase()
      const typeMap = {
        router: 'router', switch: 'switch', firewall: 'firewall',
        terminal: 'pc', wireless: 'ap', other: 'pc',
        server: 'server', camera: 'camera', nvr: 'nvr', ac: 'ac',
        laptop: 'laptop', phone: 'phone', printer: 'printer', ips: 'ips',
        lb: 'lb', sdwan: 'sdwan', behavior: 'behavior',
      }
      let devType = typeMap[cat] || 'pc'
      // 运营商/电路/传输网映射为云朵 (eNSP 惯例): 看名称而非类别,
      // "电信200M/联通100M/MPLSVPN/电信电路接入" 无论 AI 给什么类别都应是云
      if (/电信|联通|移动|电路|运营商|互联网|internet|mpls|专线|传输|宽带|出口带宽|\d{2,4}\s*m\b/i.test(lbl)
          && !/路由器|交换机|防火墙|控制器|管理|服务器|上网行为|sdwan|负载/.test(lbl)) {
        devType = 'cloud'
      }
      // 常见设备按名称兜底 (AI 把特殊设备归为 other 时)
      if (devType === 'pc') {
        if (/负载均衡/.test(lbl)) devType = 'lb'
        else if (/上网行为|行为管理|流控/.test(lbl)) devType = 'behavior'
        else if (/sdwan/i.test(lbl)) devType = 'sdwan'
        else if (/服务器|认证|堡垒机|portal/i.test(lbl)) devType = 'server'
      }
      // 无线控制器被误归为 AP 时按名称纠正
      if (devType === 'ap' && /控制器|(^|[^a-z])ac($|[^a-z])/i.test(lbl)) devType = 'ac'
      nodeDataArray.push({
        key: key,
        category: normalizeCategory(devType),
        label: node.label || node.hostname || key,
        role: node.role || 'endpoint',
        model: node.model || 'unknown',
        hostname: node.hostname || node.label || key,
        mgmtIp: node.mgmtIp || '',
        mgmtVlan: node.mgmtVlan || '',
        description: node.description || node.zone || '',
        loc: go.Point.stringify(new go.Point(pos.x, pos.y)),
      })
    }

    // Build linkDataArray: 冗余的 "A→B/A至B" 型标签直接去掉 (连线本身已表达),
    // 只保留有信息量的短标签 (如 "SDWAN链路"/"办公无线网段 10.94.88.0/24")
    const isRedundant = (label, from, to) => {
      if (!label) return true
      const a = (nodes[from]?.label || nodes[from]?.hostname || from || '').trim()
      const b = (nodes[to]?.label || nodes[to]?.hostname || to || '').trim()
      if (label.includes('→')) return true
      // 形如 "A至B" 且 A/B 是两端设备名
      const m = label.match(/^(.+?)至(.+)$/)
      if (m && ((a.includes(m[1]) && b.includes(m[2])) || (b.includes(m[1]) && a.includes(m[2])))) return true
      // 标签同时包含两端名称且无 IP/端口等附加信息
      if (label.includes(a) && label.includes(b) && a && b && !/\d{1,3}\.\d{1,3}/.test(label)) return true
      return false
    }
    const linkDataArray = links.map((link) => {
      const raw = link.linkLabel || ''
      const kept = isRedundant(raw, link.from, link.to) ? '' : raw
      return {
        from: link.from,
        to: link.to,
        fromPort: link.fromPort || '',
        toPort: link.toPort || '',
        // AI 未给出链路属性时, 按 mode/bandwidth/redundancy 自动生成
        // (如 "Trunk · 10GE" / "Access" / "三层互联 · 10GE · （备）")
        linkLabel: kept || autoLinkLabel(link),
        mode: link.mode || 'access',
        accessVlan: link.accessVlan || null,
        allowedVlans: link.allowedVlans || [],
        nativeVlan: link.nativeVlan || 1,
        bandwidth: link.bandwidth || '',
        redundancy: link.redundancy || '',
      }
    })

    // 安全域分区框: 仅当 AI 从原图提取到分组框时才画 (忠实原图, 不脑补)
    const zoneNodes = buildZoneNodes(topoData, positions)

    // Load onto canvas (重新挂载模板表, 自愈任何模板丢失的情况)
    diagram.nodeTemplateMap = createNodeTemplateMap()
    diagram.model = new go.GraphLinksModel({
      nodeDataArray: [...zoneNodes, ...nodeDataArray],
      linkDataArray: linkDataArray,
      nodeCategoryProperty: 'category',
      nodeLayerKeyProperty: 'layerName',
    })

    // Rebuild modelCounters from node keys
    for (const k of Object.keys(modelCounters)) delete modelCounters[k]
    for (const n of nodeDataArray) {
      const match = n.key?.match(/^(.+)_(\d+)$/)
      if (match) {
        const base = match[1]
        const num = parseInt(match[2], 10)
        if (!modelCounters[base] || modelCounters[base] < num) {
          modelCounters[base] = num
        }
      }
    }

    saveModel()
  } catch (e) {
    console.error('Import topology from analysis failed:', e)
    alert('拓扑导入失败：' + e.message)
  }
}

function _computeLayout(topoData) {
  // 真实网工拓扑布局: 自上而下按网络层级分行, 行内按邻居重心排序减少交叉
  // 层级: 0出口/运营商 → 1外网防火墙 → 2DMZ/安全 → 3内网防火墙 → 4核心 → 5汇聚 → 6接入 → 7无线 → 8终端/服务器
  const nodes = topoData.nodes || {}
  const links = topoData.links || []
  const positions = new Map()

  const labelOf = (key) => (nodes[key]?.label || nodes[key]?.hostname || key || '')
  const has = (s, ...kws) => kws.some(k => s.includes(k))

  // ---- 1) 分层 ----
  const tierOf = (key, node) => {
    const label = labelOf(key)
    const l = label.toLowerCase()
    const zone = node.zone || ''
    const z = zone.toLowerCase()
    const role = node.role || ''
    const cat = node.category || ''

    if (has(z, '外部', '互联网', 'internet', 'wan', 'dmz')) {
      if (z.includes('dmz')) return 2
      return 0
    }
    if (has(l, '防火墙')) return has(l, '外', 'internet') ? 1 : 5 // 内网防火墙=服务器区边界, 与汇聚层同行
    if (has(l, '核心')) return has(l, 'wifi', '无线') ? 7 : 4
    if (has(l, '汇聚')) return has(l, 'wifi', '无线') ? 7 : 5
    // 运营商/电路名称的节点固定在顶层 (出口层)
    if (/电信|联通|移动|电路|运营商|互联网|internet|mpls|专线|传输|宽带/i.test(l)
        && !/路由器|交换机|防火墙|控制器|管理|服务器/.test(l)) return 0
    // 新设备类别: 负载均衡/SDWAN 在出口层, 上网行为管理串接在出口防火墙与核心之间
    if (cat === 'lb' || cat === 'sdwan' || /负载均衡|sdwan/i.test(l)) return 0
    if (cat === 'behavior' || /上网行为|行为管理|流控/.test(l)) return 2
    if (has(l, 'wifi', '无线') || has(z, '无线')) return 7
    if (cat === 'wireless' || role === 'wireless' || /\bap\b|(^|[^a-z])ap(_|-|[0-9])/i.test(l)) return 8
    if (cat === 'switch' || role === 'access') return 6
    if (cat === 'router' || role === 'router') return 0
    return 8 // 终端/服务器
  }

  const TIERS = 9
  const tiers = Array.from({ length: TIERS }, () => [])
  for (const [key, node] of Object.entries(nodes)) {
    tiers[Math.min(tierOf(key, node), TIERS - 1)].push(key)
  }
  // 空层不占行高: 非空层依次压缩排列
  const rowOfTier = new Map()
  let nextRow = 0
  for (let t = 0; t < TIERS; t++) {
    if (tiers[t].length) rowOfTier.set(t, nextRow++)
  }

  // ---- 2) 行内排序: 上面各层已放置节点的 x 重心 (barycenter), 减少连线交叉 ----
  const placed = new Set()
  const layoutRows = [] // 供安全域分区框定位: { tier, y, minX, maxX }
  const placeRow = (rowKeys, y, tier) => {
    // 估算每个节点宽度: 中文字符按 12px, 其他 7px, 加图标区
    const widthOf = (key) => {
      const label = labelOf(key)
      let w = 0
      for (const ch of label) w += /[\u4e00-\u9fa5]/.test(ch) ? 12 : 7
      return Math.min(Math.max(w + 78, 130), 240)
    }
    const gap = 72
    const totalWidth = rowKeys.reduce((s, k) => s + widthOf(k), 0) + gap * (rowKeys.length - 1)
    let x = CENTER_X - totalWidth / 2
    const startX = x
    for (const key of rowKeys) {
      const w = widthOf(key)
      positions.set(key, { x: x + w / 2, y })
      placed.add(key)
      x += w + gap
    }
    layoutRows.push({ tier, y, minX: startX, maxX: x - gap })
  }

  const CENTER_X = 900
  const ROW_H = 215

  // 第 0 层: 无参照, 按名称排序 (主/备自然相邻)
  if (tiers[0].length) {
    tiers[0].sort((a, b) => labelOf(a).localeCompare(labelOf(b), 'zh'))
    placeRow(tiers[0], 80, 0)
  }

  for (let t = 1; t < TIERS; t++) {
    if (!tiers[t].length) continue
    const row = tiers[t].map(key => {
      const xs = []
      for (const l of links) {
        let other = null
        if (l.from === key && placed.has(l.to)) other = l.to
        else if (l.to === key && placed.has(l.from)) other = l.from
        if (other) xs.push(positions.get(other).x)
      }
      return {
        key,
        avg: xs.length ? xs.reduce((s, v) => s + v, 0) / xs.length : Infinity,
      }
    })
    // 有连线的按重心排, 无连线的按名称排放在后面
    row.sort((a, b) => {
      if (a.avg !== b.avg) {
        if (a.avg === Infinity) return 1
        if (b.avg === Infinity) return -1
        return a.avg - b.avg
      }
      return labelOf(a.key).localeCompare(labelOf(b.key), 'zh')
    })
    placeRow(row.map(r => r.key), 80 + (rowOfTier.get(t) ?? t) * ROW_H, t)
  }

  return { positions, rows: layoutRows }
}

// ---- Context menu ----
function onContextMenu(ev) {
  if (!diagram) return
  const rect = canvasRef.value.getBoundingClientRect()
  const x = ev.clientX
  const y = ev.clientY
  const canvasPoint = diagram.transformViewToDoc(new go.Point(ev.clientX - rect.left, ev.clientY - rect.top))
  const part = diagram.findPartAt(canvasPoint, false)

  let items = []
  let targetType = 'canvas'
  let targetData = null

  // 分区框 (zone) 视为画布空白, 右键不出设备菜单
  if (part instanceof go.Node && part.data?.category === 'zone') part = null

  if (part instanceof go.Node) {
    targetType = 'node'
    targetData = { ...part.data }
    items = [
      { label: '打开命令行', icon: Monitor, action: 'open-cli' },
      { label: '编辑属性', icon: Edit, action: 'edit-props' },
      { divider: true },
      { label: '复制设备', icon: CopyDocument, action: 'copy-device', shortcut: 'Ctrl+C' },
      { label: '导出该设备配置', icon: Download, action: 'export-device' },
      { divider: true },
      { label: '删除设备', icon: Delete, action: 'delete-device', danger: true, shortcut: 'Del' },
    ]
  } else if (part instanceof go.Link) {
    targetType = 'link'
    targetData = { ...part.data }
    const isBondedLink = part.data.bonded || part.data.ethTrunkId != null
    items = [
      { label: isBondedLink ? '编辑 Eth-Trunk / VLAN' : '编辑 VLAN / 端口', icon: Link, action: 'edit-link' },
      { divider: true },
      { label: '删除链路', icon: Delete, action: 'delete-link', danger: true },
    ]
  } else {
    targetType = 'canvas'
    items = [
      { label: '粘贴设备', icon: CopyDocument, action: 'paste-device', shortcut: copiedNodeData ? 'Ctrl+V' : '' },
      { divider: true },
      { label: '导出为图片', icon: Camera, action: 'export-image' },
      { divider: true },
      { label: '清空画布', icon: Delete, action: 'clear-canvas', danger: true },
    ]
  }

  ctxMenuTargetPart = part
  ctxMenu.value = { visible: true, x, y, items, targetType, targetData }
}

function closeContextMenu() {
  ctxMenu.value = { visible: false, x: 0, y: 0, items: [], targetType: null, targetData: null }
}

function handleContextAction(action) {
  const td = ctxMenu.value.targetData
  closeContextMenu()

  switch (action) {
    case 'open-cli':
      emit('open-cli', td)
      break
    case 'edit-props':
      emit('edit-device', td)
      break
    case 'copy-device':
      if (td) {
        copiedNodeData = { ...td }
        // Don't copy the loc — will be placed at drop/paste position
        delete copiedNodeData.loc
        delete copiedNodeData.key
      }
      break
    case 'paste-device': {
      if (!copiedNodeData || !diagram) return
      const key = `${copiedNodeData.model || 'device'}_${Date.now()}`
      const pos = diagram.transformViewToDoc(new go.Point(ctxMenu.value.x, ctxMenu.value.y))
      diagram.model.addNodeData({
        ...copiedNodeData,
        key,
        loc: go.Point.stringify(pos),
      })
      break
    }
    case 'export-device':
      emit('export-device-config', td)
      break
    case 'delete-device':
      if (td?.key) deleteNode(td.key)
      break
    case 'edit-link':
      if (ctxMenuTargetPart instanceof go.Link) {
        openLinkConfig(ctxMenuTargetPart.data)
      }
      break
    case 'delete-link':
      if (ctxMenuTargetPart instanceof go.Link) {
        diagram.select(ctxMenuTargetPart)
        diagram.commandHandler.deleteSelection()
      }
      break
    case 'export-image':
      exportToImage('png')
      break
    case 'clear-canvas':
      clearTopology()
      break
  }
}

// Click anywhere to close context menu
function onDocClick() { closeContextMenu() }

function focusDevice(deviceKey) {
  if (!diagram) return
  const node = diagram.findNodeForKey(deviceKey)
  if (node) {
    diagram.select(node)
    diagram.centerRect(node.actualBounds)
  }
}

function applyTemplate(templateData) {
  if (!diagram) return
  // templateData is { nodes: {...}, links: [...] }
  importTopologyFromAnalysis(templateData)
}

async function autoLayout() {
  if (!diagram) {
    ElMessage.warning('拓扑图未初始化，请刷新页面')
    return
  }
  if (!diagram.nodes) {
    ElMessage.warning('拓扑图节点集合不可用')
    return
  }
  const nodeArr = []
  diagram.nodes.each(n => nodeArr.push(n))
  if (nodeArr.length < 2) {
    ElMessage.info('设备数量少于 2 台，无需自动布局')
    return
  }

  const msg = ElMessage({ message: `正在自动布局 ${nodeArr.length} 台设备...`, type: 'info', duration: 0 })
  await new Promise(r => requestAnimationFrame(r))

  try {
    diagram.startTransaction('auto-layout')
    // 用与识图导入相同的分层布局算法 (出口→防火墙→核心→汇聚→接入→无线→终端)
    const nodes = {}
    diagram.nodes.each(n => {
      const d = n.data
      if (d.category === 'zone') return // 分区框不参与布局
      nodes[d.key] = { label: d.label, role: d.role, category: d.category === 'pc' ? 'terminal' : d.category, zone: d.description || '' }
    })
    const links = []
    diagram.links.each(l => {
      const d = l.data
      if (d?.from && d?.to) links.push({ from: d.from, to: d.to })
    })
    const { positions } = _computeLayout({ nodes, links })
    for (const [key, pos] of positions.entries()) {
      const node = diagram.findNodeForKey(key)
      if (node) node.location = new go.Point(pos.x, pos.y)
    }
    diagram.commitTransaction('auto-layout')
    msg.close()
    ElMessage.success(`自动布局完成，已排列 ${nodeArr.length} 台设备`)
  } catch (e) {
    try { diagram.commitTransaction('auto-layout') } catch (_) {}
    msg.close()
    console.error('autoLayout error:', e)
    ElMessage.error('自动布局失败：' + (e.message || e))
  }
}

// ---- 图例合成到导出图 (HTML 浮层不会进入 GoJS 导出, 需手动绘制) ----
let legendImgCache = null
function getLegendImages() {
  if (legendImgCache) return legendImgCache
  legendImgCache = legendItems.map(it => {
    const img = new Image()
    if (it.img) {
      img.src = it.img
    } else {
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(it.svg)
    }
    return img
  })
  return legendImgCache
}

async function legendImgToDataUrl(img) {
  // 把已加载的图例图转成 dataURL (供 SVG 导出内嵌)
  if (!img.complete || !img.naturalWidth) return null
  const c = document.createElement('canvas')
  c.width = img.naturalWidth
  c.height = img.naturalHeight
  c.getContext('2d').drawImage(img, 0, 0)
  try { return c.toDataURL('image/png') } catch (_) { return null }
}

function roundRectPath(ctx, x, y, w, h, r) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

async function compositeLegend(dataUri, mimeType) {
  const imgs = getLegendImages()
  try { await Promise.all(imgs.map(i => i.decode().catch(() => {}))) } catch (_) {}
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => {
      const s = 2            // 图例绘制倍率, 与导出 scale 对齐保证清晰
      const pad = 60 * s     // 导出图四周留白
      const canvas = document.createElement('canvas')
      canvas.width = img.width + pad * 2
      canvas.height = img.height + pad * 2
      const ctx = canvas.getContext('2d')
      if (mimeType === 'image/jpeg') {
        ctx.fillStyle = '#ffffff'
        ctx.fillRect(0, 0, canvas.width, canvas.height)
      }
      ctx.drawImage(img, pad, pad)

      // ---- 画图例卡片 (右下角) ----
      const rowH = 36 * s
      const cardW = 230 * s
      const cardPad = 14 * s
      const titleH = 34 * s
      const cardH = titleH + legendItems.length * rowH + cardPad * 2
      const cx = canvas.width - cardW - 24 * s
      const cy = canvas.height - cardH - 24 * s
      ctx.fillStyle = 'rgba(255,255,255,0.97)'
      ctx.strokeStyle = '#cfd8dc'
      ctx.lineWidth = 1.2 * s
      roundRectPath(ctx, cx, cy, cardW, cardH, 10 * s)
      ctx.fill()
      ctx.stroke()
      ctx.fillStyle = '#37474F'
      ctx.font = `bold ${16 * s}px "Microsoft YaHei", sans-serif`
      ctx.textBaseline = 'middle'
      ctx.fillText('图  例', cx + cardPad, cy + cardPad + titleH / 2 - 4 * s)
      let iy = cy + cardPad + titleH
      legendItems.forEach((it, idx) => {
        const icon = imgs[idx]
        const ih = 26 * s
        const iw = ih * (icon.width && icon.height ? icon.width / icon.height : 1.4)
        if (icon.complete && icon.naturalWidth) {
          ctx.drawImage(icon, cx + cardPad, iy + (rowH - ih) / 2, Math.min(iw, 44 * s), ih)
        }
        ctx.fillStyle = '#455A64'
        ctx.font = `${14 * s}px "Microsoft YaHei", sans-serif`
        ctx.fillText(it.name, cx + cardPad + 56 * s, iy + rowH / 2)
        iy += rowH
      })
      resolve(canvas.toDataURL(mimeType))
    }
    img.onerror = () => resolve(dataUri)   // 合成失败则退回原图
    img.src = dataUri
  })
}

async function exportToImage(format = 'png') {
  if (!diagram) {
    ElMessage.warning('拓扑图未初始化')
    return
  }
  if (!diagram.model.nodeDataArray || diagram.model.nodeDataArray.length === 0) {
    ElMessage.error('拓扑图为空，无法导出')
    return
  }

  try {
    // 按文档实际边界导出完整拓扑: 显式指定 position/size, 避免默认 maxSize 2000x2000 裁切
    const db = diagram.documentBounds
    const capW = 4200  // 输出最长边上限, 自适应 scale
    const fitScale = Math.min(2.5, capW / Math.max(db.width, db.height, 1))

    if (format === 'svg') {
      const svgEl = diagram.makeSvg({
        scale: Math.min(1.5, capW / Math.max(db.width, db.height, 1)),
        background: 'white',
        maxSize: new go.Size(8192, 8192),
      })
      await appendLegendToSvg(svgEl)
      const blob = new Blob([svgEl.outerHTML], { type: 'image/svg+xml;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      downloadBlob(url, `topology-${Date.now()}.svg`)
      URL.revokeObjectURL(url)
      ElMessage.success('拓扑图已导出为 SVG (含图例)')
    } else {
      const mimeType = format === 'jpeg' ? 'image/jpeg' : 'image/png'
      const ext = format === 'jpeg' ? 'jpg' : 'png'
      const dataUri = diagram.makeImageData({
        scale: fitScale,
        background: 'white',
        type: mimeType,
        maxSize: new go.Size(8192, 8192),
        padding: new go.Margin(40, 40, 40, 40),
      })
      const merged = await compositeLegend(dataUri, mimeType)
      const blob = dataUriToBlob(merged)
      const url = URL.createObjectURL(blob)
      downloadBlob(url, `topology-${Date.now()}.${ext}`)
      URL.revokeObjectURL(url)
      ElMessage.success(`拓扑图已导出为 ${ext.toUpperCase()} (含图例)`)
    }
  } catch (e) {
    console.error('exportToImage error:', e)
    ElMessage.error('导出图片失败：' + (e.message || e))
  }
}

// SVG 导出: 在 SVG 末尾追加图例组 (图片项内嵌为 dataURL)
async function appendLegendToSvg(svgEl) {
  try {
    const imgs = getLegendImages()
    try { await Promise.all(imgs.map(i => i.decode().catch(() => {}))) } catch (_) {}
    const dataUrls = await Promise.all(imgs.map(i => legendImgToDataUrl(i)))
    const ns = 'http://www.w3.org/2000/svg'
    const rowH = 36, cardPad = 14, titleH = 34, cardW = 230
    const cardH = titleH + legendItems.length * rowH + cardPad * 2
    const W = parseFloat(svgEl.getAttribute('width')) || svgEl.viewBox?.baseVal?.width || 1000
    const H = parseFloat(svgEl.getAttribute('height')) || svgEl.viewBox?.baseVal?.height || 800
    const g = document.createElementNS(ns, 'g')
    g.setAttribute('transform', `translate(${W - cardW - 24},${H - cardH - 24})`)
    const rect = document.createElementNS(ns, 'rect')
    rect.setAttribute('width', cardW); rect.setAttribute('height', cardH)
    rect.setAttribute('rx', 10); rect.setAttribute('fill', 'rgba(255,255,255,0.97)')
    rect.setAttribute('stroke', '#cfd8dc')
    g.appendChild(rect)
    const title = document.createElementNS(ns, 'text')
    title.setAttribute('x', cardPad); title.setAttribute('y', cardPad + titleH / 2)
    title.setAttribute('font-size', 16); title.setAttribute('font-weight', 'bold')
    title.setAttribute('fill', '#37474F'); title.setAttribute('font-family', 'Microsoft YaHei, sans-serif')
    title.textContent = '图  例'
    g.appendChild(title)
    legendItems.forEach((it, idx) => {
      const y = cardPad + titleH + idx * rowH
      const du = dataUrls[idx]
      if (du) {
        const image = document.createElementNS(ns, 'image')
        image.setAttribute('href', du)
        image.setAttribute('x', cardPad)
        image.setAttribute('y', y + 4)
        image.setAttribute('width', 40)
        image.setAttribute('height', 28)
        image.setAttribute('preserveAspectRatio', 'xMidYMid meet')
        g.appendChild(image)
      } else if (it.svg) {
        const wrapper = document.createElementNS(ns, 'g')
        wrapper.setAttribute('transform', `translate(${cardPad},${y + 5}) scale(0.75)`)
        const tmp = document.createElementNS(ns, 'g')
        tmp.innerHTML = it.svg
        const inner = tmp.querySelector('svg')
        if (inner) {
          while (inner.firstChild) wrapper.appendChild(inner.firstChild)
        }
        g.appendChild(wrapper)
      }
      const label = document.createElementNS(ns, 'text')
      label.setAttribute('x', cardPad + 56); label.setAttribute('y', y + rowH / 2 + 5)
      label.setAttribute('font-size', 14); label.setAttribute('fill', '#455A64')
      label.setAttribute('font-family', 'Microsoft YaHei, sans-serif')
      label.textContent = it.name
      g.appendChild(label)
    })
    svgEl.appendChild(g)
  } catch (_) {}
}

function dataUriToBlob(dataUri) {
  const parts = dataUri.split(',')
  const mime = parts[0].match(/:(.*?);/)[1]
  const bytes = atob(parts[1])
  const arr = new Uint8Array(bytes.length)
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
  return new Blob([arr], { type: mime })
}

function downloadBlob(url, filename) {
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

defineExpose({ getTopologyData, selectedNodeData, updateNodeData, deleteNode, exportTopologyFile, importTopologyFile, clearTopology, importTopologyFromAnalysis, focusDevice, applyTemplate, autoLayout, exportToImage })

// ---- Topology persistence ----
function saveModel() {
  if (!diagram) return
  try {
    const json = diagram.model.toJson()
    localStorage.setItem(TOPO_STORAGE_KEY, json)
    // Also persist modelCounters so keys don't collide on reload
    localStorage.setItem('topo-counters', JSON.stringify(modelCounters))
  } catch (_) {}
}

function scheduleSave() {
  clearTimeout(saveTimer)
  saveTimer = setTimeout(saveModel, 300)
}

// ---- Diagram setup ----
onMounted(() => {
  document.addEventListener('click', onDocClick)

  diagram = $(go.Diagram, canvasRef.value, {
    'undoManager.isEnabled': true,
    initialContentAlignment: go.Spot.Center,
    allowDrop: false,  // GoJS 不接管外部拖放, 由自定义 @drop 处理 (否则会生成默认文字节点)
    allowDelete: true,
    scrollMode: go.Diagram.InfiniteScroll,
    'draggingTool.isEnabled': true,
    'toolManager.mouseWheelBehavior': go.ToolManager.WheelZoom,

    grid: createGridPattern(),
    'grid.visible': true,

    'nodeSelectionAdornmentTemplate': $(
      go.Adornment, 'Auto',
      $(go.Shape, 'Rectangle', {
        fill: null,
        stroke: '#1976D2',
        strokeWidth: 2,
        strokeDashArray: [4, 2],
      })
    ),

    'linkingTool.isEnabled': true,
    'linkingTool.portGravity': 25,
    'linkingTool.archetypeLinkData': { linkLabel: '', linkColor: '#78909C', ethTrunkId: null, memberPortsFrom: [], memberPortsTo: [], lacpMode: 'static', loadBalance: 'src-dst-ip', bandwidth: '10GE', bonded: false },
    'linkingTool.temporaryLink': $(
      go.Link,
      { curve: go.Link.None },
      $(go.Shape, { stroke: '#EF5350', strokeWidth: 2, strokeDashArray: [4, 3] })
    ),
    'relinkingTool.isEnabled': false,
  })

  diagram.nodeTemplateMap = createNodeTemplateMap()

  diagram.linkTemplate =
    $(go.Link,
      { routing: go.Link.Orthogonal, curve: go.Link.None, corner: 6 },
      $(go.Shape, {
        stroke: '#78909C',
        strokeWidth: 2,
      }, new go.Binding('stroke', 'linkColor'), new go.Binding('strokeWidth', 'linkStrokeWidth')),
      $(go.Shape, {
        toArrow: 'Standard',
        stroke: '#78909C',
        fill: '#78909C',
        scale: 1.3,
      }, new go.Binding('stroke', 'linkColor'), new go.Binding('fill', 'linkColor')),
      $(go.TextBlock, {
        segmentOffset: new go.Point(0, -11),
        font: 'bold 9px "Microsoft YaHei", sans-serif',
        stroke: '#37474F',
        background: 'rgba(255,255,255,0.92)',
        margin: new go.Margin(1, 3),
        maxLines: 2,
        overflow: go.TextBlock.Ellipsis,
        wrap: go.TextBlock.WrapFit,
        width: 150,
        segmentOrientation: go.Link.OrientNone,  // 永远水平, 不随竖线旋转
        cursor: 'pointer',
      }, new go.Binding('text', 'linkLabel'))
    )

  // Auto-set link label when link is created, then open config dialog
  diagram.addModelChangedListener(evt => {
    if (evt.change === go.ChangedEvent.LinkConnected && evt.propertyName === 'fromNode') {
      const linkData = evt.subject?.data
      if (!linkData) return
      const model = diagram.model
      const fromNode = model.findNodeDataForKey(linkData.from)
      const toNode = model.findNodeDataForKey(linkData.to)
      if (!fromNode || !toNode) return
      const props = getLinkProperties(fromNode, toNode)
      const baseLabel = `${props.label === 'Eth-Trunk' ? 'Eth-Trunk' : props.bandwidth}`
      model.setDataProperty(linkData, 'linkLabel', baseLabel)
      model.setDataProperty(linkData, 'linkColor', props.color)
      model.setDataProperty(linkData, 'linkStrokeWidth', props.strokeWidth || 2)
      model.setDataProperty(linkData, 'linkMode', props.label === 'Eth-Trunk' ? 'trunk' : props.label === 'Trunk' ? 'trunk' : 'access')
      model.setDataProperty(linkData, 'bonded', props.bonded || false)
      model.setDataProperty(linkData, 'bandwidth', props.bandwidth || '10GE')
      if (props.bonded) {
        model.setDataProperty(linkData, 'ethTrunkId', null) // user will set in dialog
        model.setDataProperty(linkData, 'memberPortsFrom', [])
        model.setDataProperty(linkData, 'memberPortsTo', [])
        model.setDataProperty(linkData, 'lacpMode', 'static')
        model.setDataProperty(linkData, 'loadBalance', 'src-dst-ip')
      }
      // Auto-open VLAN config dialog for new links
      currentLinkKey = linkData.__gohashid
      nextTick(() => openLinkConfig(linkData))
    }
  })

  // Double-click link to edit VLAN config
  diagram.addDiagramListener('ObjectDoubleClicked', e => {
    const part = e.subject.part
    if (part instanceof go.Link) {
      openLinkConfig(part.data)
    }
  })

  // Single-click node → update selection state
  diagram.addDiagramListener('ObjectSingleClicked', e => {
    const part = e.subject.part
    if (part instanceof go.Node) {
      selectedNodeData.value = { ...part.data }
    } else {
      selectedNodeData.value = null
    }
  })

  // Click background → deselect
  diagram.addDiagramListener('BackgroundSingleClicked', () => {
    selectedNodeData.value = null
  })

  // Restore saved topology or start fresh
  let loaded = false
  try {
    const savedJson = localStorage.getItem(TOPO_STORAGE_KEY)
    if (savedJson) {
      const restored = go.Model.fromJson(savedJson)
      if (restored instanceof go.GraphLinksModel) restored.nodeLayerKeyProperty = 'layerName'
      // 净化历史数据的 category：老版本可能存了模板表外的值，导致节点回退成纯文字
      restored.nodeDataArray.forEach(n => {
        const fixed = normalizeCategory(n.category)
        if (fixed !== n.category) n.category = fixed
      })
      diagram.model = restored
      const sc = localStorage.getItem('topo-counters')
      if (sc) Object.assign(modelCounters, JSON.parse(sc))
      loaded = true
    }
  } catch (_) {}

  if (!loaded) {
    diagram.model = new go.GraphLinksModel({
      nodeDataArray: [],
      linkDataArray: [],
      nodeCategoryProperty: 'category',
      nodeLayerKeyProperty: 'layerName',
    })
  }

  // Persist topology on any model change (debounced)
  diagram.addModelChangedListener(() => scheduleSave())
  // 调试/测试出口: 便于自动化测试定位节点与画布坐标
  window.__topoDiagram = diagram
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  if (window.__topoDiagram) window.__topoDiagram = null
  if (diagram) {
    diagram.div = null
    diagram = null
  }
})
</script>

<style scoped>
/* ============ 画布容器 + 图例 ============ */
.canvas-wrap {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
}
.canvas-legend {
  position: absolute;
  right: 14px;
  bottom: 14px;
  z-index: 10;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid #cfd8dc;
  border-radius: 8px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.12);
  backdrop-filter: blur(4px);
  min-width: 110px;
  max-width: 240px;
  user-select: none;
}
.legend-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 5px 10px;
  cursor: pointer;
  border-bottom: 1px solid #eceff1;
}
.canvas-legend.collapsed .legend-header { border-bottom: none; }
.legend-title {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.35em;
  color: #455a64;
}
.legend-toggle { font-size: 11px; color: #90a4ae; }
.legend-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2px 8px;
  padding: 7px 10px 9px;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 5px;
}
.legend-icon { display: inline-flex; flex-shrink: 0; }
.legend-img {
  height: 30px;
  max-width: 64px;
  object-fit: contain;
  background: #fff;
  border: 1px solid #cfd8dc;
  border-radius: 3px;
  flex-shrink: 0;
}
.legend-name {
  font-size: 11px;
  color: #37474f;
  white-space: nowrap;
}
:global(.dark) .canvas-legend,
html.dark .canvas-legend {
  background: rgba(30, 41, 59, 0.94);
  border-color: #455a64;
}
html.dark .legend-title { color: #b0bec5; }
html.dark .legend-name { color: #cfd8dc; }
html.dark .legend-header { border-bottom-color: #37474f; }

#topologyCanvas {
  background: #f8f9fa;
  min-height: 500px;
}
</style>

<style>
/* Context menu — not scoped so teleport works */
.canvas-context-menu {
  position: fixed;
  z-index: 10000;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.15);
  padding: 4px 0;
  min-width: 200px;
  user-select: none;
}
.ctx-menu-item {
  display: flex;
  align-items: center;
  padding: 7px 16px;
  font-size: 13px;
  color: #303133;
  cursor: pointer;
  transition: background 0.12s;
}
.ctx-menu-item:hover {
  background: #ecf5ff;
  color: #409EFF;
}
.ctx-menu-divider {
  height: 1px;
  background: #ebeef5;
  margin: 4px 8px;
  padding: 0;
  cursor: default;
  pointer-events: none;
}
.ctx-menu-danger {
  color: #F56C6C;
}
.ctx-menu-danger:hover {
  background: #fef0f0;
  color: #F56C6C;
}
.ctx-shortcut {
  margin-left: auto;
  font-size: 11px;
  color: #c0c4cc;
}
</style>
