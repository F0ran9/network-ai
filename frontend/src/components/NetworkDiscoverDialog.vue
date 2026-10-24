<template>
  <el-dialog
    v-model="visible"
    title="网络自动发现"
    width="640px"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <el-alert type="info" :closable="false" style="margin-bottom:14px"
      title="从一台种子设备出发，通过 LLDP/CDP 邻居表递归发现整网拓扑并生成诊断报告（支持华为/H3C/思科/锐捷）" />

    <el-form label-width="110px" label-position="left">
      <el-form-item label="演示模式">
        <el-switch v-model="form.demo" />
        <span class="form-tip" style="margin-left:10px">不连接真实设备，返回示例园区网数据用于预览</span>
      </el-form-item>
      <template v-if="!form.demo">
        <el-form-item label="种子设备 IP">
          <el-input v-model="form.seedIp" placeholder="核心交换机管理 IP，如 10.94.89.1" />
        </el-form-item>
        <el-form-item label="厂商">
          <el-select v-model="form.vendor" style="width:100%">
            <el-option label="华为 Huawei" value="huawei" />
            <el-option label="新华三 H3C" value="h3c" />
            <el-option label="思科 Cisco" value="cisco" />
            <el-option label="锐捷 Ruijie" value="ruijie" />
          </el-select>
        </el-form-item>
        <el-form-item label="SSH 账号">
          <el-input v-model="form.username" placeholder="admin" style="width:200px" />
          <el-input v-model="form.password" type="password" show-password
            placeholder="SSH 密码" style="width:200px; margin-left:10px" />
        </el-form-item>
        <el-form-item label="SSH 端口 / 跳数">
          <el-input-number v-model="form.sshPort" :min="1" :max="65535" style="width:140px" />
          <el-input-number v-model="form.maxDepth" :min="1" :max="6" style="width:140px; margin-left:10px" />
          <span class="form-tip" style="margin-left:10px">跳数越大扫描越全，耗时越长</span>
        </el-form-item>
      </template>
    </el-form>

    <!-- 扫描进度 -->
    <div v-if="logs.length" class="scan-log">
      <div v-for="(l, i) in logs" :key="i" class="log-line" :class="logClass(l)">{{ l }}</div>
      <div v-if="running" class="log-line scanning">扫描中…</div>
    </div>

    <!-- 诊断报告 -->
    <template v-if="result">
      <el-divider content-position="left">扫描结果</el-divider>
      <div class="stats-row">
        <el-tag>设备 {{ result.stats.devices }}</el-tag>
        <el-tag type="success">链路 {{ result.stats.links }}</el-tag>
        <el-tag type="info">成功采集 {{ result.stats.scanned }}</el-tag>
        <el-tag type="warning">诊断 {{ result.diagnostics.length }}</el-tag>
        <span class="form-tip">{{ result.stats.time }}</span>
      </div>

      <!-- 拓扑预览图 -->
      <template v-if="preview">
        <el-divider content-position="left">拓扑预览 <span class="form-tip">（按层级自动排布，悬停查看端口）</span></el-divider>
        <div class="topo-preview">
          <svg :viewBox="`0 0 ${preview.W} ${preview.H}`" xmlns="http://www.w3.org/2000/svg">
            <line v-for="(e, i) in preview.edges" :key="'e' + i"
              :x1="e.x1" :y1="e.y1" :x2="e.x2" :y2="e.y2"
              stroke="#b9c8d3" stroke-width="1.5">
              <title>{{ e.title }}</title>
            </line>
            <g v-for="(n, i) in preview.nodes" :key="'n' + i" :transform="`translate(${n.x},${n.y})`">
              <rect :x="-52" :y="-15" width="104" height="30" rx="6"
                :fill="n.color" :opacity="n.fail ? 0.55 : 0.92"
                :stroke="n.fail ? '#f56c6c' : 'none'" stroke-dasharray="4 2" stroke-width="1.5" />
              <text y="4" text-anchor="middle" font-size="11" fill="#fff" font-weight="600">{{ n.short }}</text>
              <text :y="28" text-anchor="middle" font-size="10" fill="#8a97a3" font-family="Consolas, monospace">{{ n.ip || '—' }}</text>
              <title>{{ n.label }}{{ n.ip ? '（' + n.ip + '）' : '' }}{{ n.fail ? ' · SSH 采集失败' : '' }}</title>
            </g>
          </svg>
        </div>
        <div class="preview-legend">
          <span v-for="c in legend" :key="c.name"><i :style="{ background: c.color }"></i>{{ c.name }}</span>
          <span class="form-tip">半透明红框 = SSH 采集失败</span>
        </div>
      </template>
      <div class="diag-list">
        <div v-for="(d, i) in result.diagnostics" :key="i" class="diag-item" :class="d.level">
          <span class="diag-badge">{{ d.level === 'error' ? '严重' : d.level === 'warning' ? '警告' : '提示' }}</span>
          <div>
            <b>{{ d.device }}</b>
            <span class="diag-ip" v-if="d.ip && d.ip !== '-'">（{{ d.ip }}）</span>
            <div class="diag-msg">{{ d.message }}</div>
          </div>
        </div>
      </div>
    </template>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button type="primary" :loading="running" @click="startScan" :disabled="running">
        {{ running ? '扫描中…' : '开始扫描' }}
      </el-button>
      <el-button type="success" :disabled="!result || running" @click="applyToCanvas">
        应用拓扑到画布
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { ElMessage } from 'element-plus'

const visible = ref(false)
const running = ref(false)
const logs = ref([])
const result = ref(null)

const CATEGORY_COLOR = {
  switch: '#2f7dd1', firewall: '#e6782f', router: '#8a63c9',
  ac: '#0e9e8e', ap: '#4caf50', server: '#8b6fd1',
}
const legend = [
  { name: '交换机', color: CATEGORY_COLOR.switch },
  { name: '防火墙', color: CATEGORY_COLOR.firewall },
  { name: '路由器', color: CATEGORY_COLOR.router },
  { name: '无线控制器', color: CATEGORY_COLOR.ac },
  { name: 'AP', color: CATEGORY_COLOR.ap },
  { name: '服务器', color: CATEGORY_COLOR.server },
]

// 拓扑预览: 从度数最高(优先核心角色)的节点 BFS 分层, 同层水平均排
const preview = computed(() => {
  if (!result.value) return null
  const nodes = result.value.topology.nodes || {}
  const links = result.value.topology.links || []
  const labels = Object.keys(nodes)
  if (!labels.length) return null

  const adj = {}
  labels.forEach(l => { adj[l] = [] })
  links.forEach(lk => {
    if (adj[lk.from] && adj[lk.to] && lk.from !== lk.to) {
      adj[lk.from].push(lk.to)
      adj[lk.to].push(lk.from)
    }
  })
  let root = labels[0], best = -1
  for (const l of labels) {
    const score = adj[l].length + (nodes[l].role === 'core' ? 100 : 0)
    if (score > best) { best = score; root = l }
  }
  const depth = { [root]: 0 }
  const queue = [root]
  while (queue.length) {
    const cur = queue.shift()
    for (const nb of adj[cur]) {
      if (depth[nb] === undefined) { depth[nb] = depth[cur] + 1; queue.push(nb) }
    }
  }
  const connected = labels.filter(l => depth[l] !== undefined)
  const orphan = labels.filter(l => depth[l] === undefined)
  const maxLv = Math.max(...connected.map(l => depth[l]))
  const levels = Array.from({ length: maxLv + 1 }, () => [])
  connected.forEach(l => levels[depth[l]].push(l))

  const W = 600, nodeW = 104, gapX = 10, rowH = 94
  const placed = {}
  levels.forEach((lv, li) => {
    const total = lv.length * nodeW + (lv.length - 1) * gapX
    let x = Math.max(6, (W - total) / 2)
    lv.forEach(l => { placed[l] = { x: x + nodeW / 2, y: 34 + li * rowH }; x += nodeW + gapX })
  })
  if (orphan.length) {
    const total = orphan.length * nodeW + (orphan.length - 1) * gapX
    let x = Math.max(6, (W - total) / 2)
    const y = 34 + (maxLv + 1) * rowH + 6
    orphan.forEach(l => { placed[l] = { x: x + nodeW / 2, y }; x += nodeW + gapX })
  }
  const H = 40 + (maxLv + 1 + (orphan.length ? 1 : 0)) * rowH
  const edgeEls = links
    .filter(lk => placed[lk.from] && placed[lk.to] && lk.from !== lk.to)
    .map(lk => ({
      x1: placed[lk.from].x, y1: placed[lk.from].y,
      x2: placed[lk.to].x, y2: placed[lk.to].y,
      title: `${lk.from} ↔ ${lk.to}${lk.linkLabel ? '（' + lk.linkLabel + '）' : ''}`,
    }))
  const nodeEls = labels.map(l => {
    const nd = nodes[l]
    return {
      label: l,
      short: l.length > 12 ? l.slice(0, 11) + '…' : l,
      ip: nd.mgmtIp || '',
      fail: /SSH 采集失败/.test(nd.description || ''),
      color: CATEGORY_COLOR[nd.category] || '#7a8b99',
      x: placed[l].x, y: placed[l].y,
    }
  })
  return { W, H, edges: edgeEls, nodes: nodeEls }
})

const form = reactive({
  seedIp: '', username: 'admin', password: '', vendor: 'huawei',
  sshPort: 22, maxDepth: 3, demo: false,
})

const emit = defineEmits(['apply'])

function logClass(l) {
  if (l.startsWith('✓')) return 'ok'
  if (l.startsWith('✗')) return 'err'
  return ''
}

function startScan() {
  if (!form.demo && !form.seedIp.trim()) {
    ElMessage.warning('请填写种子设备 IP（或打开演示模式）')
    return
  }
  running.value = true
  logs.value = []
  result.value = null

  fetch('/api/discover/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('tct-token')}` },
    body: JSON.stringify({ ...form }),
  }).then(async (resp) => {
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
        const line = p.split('\n').find(l => l.startsWith('data: '))
        if (!line) continue
        const evt = JSON.parse(line.slice(6))
        if (evt.type === 'progress') logs.value.push(evt.message)
        else if (evt.type === 'result') { result.value = evt.data; logs.value.push('扫描完成') }
        else if (evt.type === 'error') { logs.value.push(`扫描失败: ${evt.data}`); ElMessage.error(evt.data) }
      }
    }
  }).catch((e) => {
    ElMessage.error(e.message || '扫描请求失败')
  }).finally(() => {
    running.value = false
  })
}

function applyToCanvas() {
  if (!result.value) return
  emit('apply', result.value.topology)
  visible.value = false
  ElMessage.success(`已应用 ${result.value.stats.devices} 台设备 / ${result.value.stats.links} 条链路到画布`)
}

function open() {
  visible.value = true
}

defineExpose({ visible, open })
</script>

<style scoped>
:deep(.el-dialog__body) {
  max-height: calc(88vh - 130px);
  overflow-y: auto;
}
.form-tip { font-size: 11px; color: #909399; }
.scan-log {
  max-height: 200px; overflow-y: auto;
  background: #10232e; color: #b7d6e2; border-radius: 6px;
  font-family: Consolas, monospace; font-size: 12px;
  padding: 10px 12px; margin-top: 6px;
}
.log-line { line-height: 1.8; }
.log-line.ok { color: #67c23a; }
.log-line.err { color: #f56c6c; }
.log-line.scanning { color: #e6a23c; animation: blink 1.2s infinite; }
@keyframes blink { 50% { opacity: .4; } }
.stats-row { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; }
.diag-list { max-height: 220px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
.diag-item {
  display: flex; gap: 10px; align-items: flex-start;
  padding: 8px 10px; border-radius: 6px; font-size: 13px;
  background: #f4f7f9; border-left: 3px solid #c0c4cc;
}
.diag-item.error { border-left-color: #f56c6c; background: #fef0f0; }
.diag-item.warning { border-left-color: #e6a23c; background: #fdf6ec; }
.diag-item.info { border-left-color: #409eff; background: #ecf5ff; }
.diag-badge {
  flex-shrink: 0; font-size: 11px; padding: 1px 8px; border-radius: 999px;
  color: #fff; background: #909399; margin-top: 2px;
}
.diag-item.error .diag-badge { background: #f56c6c; }
.diag-item.warning .diag-badge { background: #e6a23c; }
.diag-item.info .diag-badge { background: #409eff; }
.diag-ip { color: #909399; font-family: Consolas, monospace; font-size: 12px; }
.diag-msg { color: #606266; margin-top: 2px; }
.topo-preview {
  background: #f7fafc; border: 1px solid #e4eaf0; border-radius: 8px;
  padding: 6px 8px 2px;
}
.topo-preview svg { width: 100%; display: block; }
.preview-legend {
  display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
  margin-top: 8px; font-size: 11px; color: #606266;
}
.preview-legend i {
  display: inline-block; width: 10px; height: 10px; border-radius: 2px;
  margin-right: 4px; vertical-align: -1px;
}
</style>
