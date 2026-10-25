<template>
  <el-dialog v-model="visible" title="审计日志 — 平台操作记录" width="86%" top="6vh"
             :close-on-click-modal="false" class="audit-panel">
    <!-- 统计条 -->
    <div class="audit-stats">
      <el-tag type="info" effect="plain">近 {{ statsDays }} 天共 {{ stats.total }} 条操作</el-tag>
      <el-tag v-if="stats.fails > 0" type="danger" effect="plain">失败 {{ stats.fails }} 次</el-tag>
      <el-tag v-for="a in stats.byAction.slice(0, 5)" :key="a.action" effect="plain">
        {{ actionLabel(a.action) }} {{ a.count }}
      </el-tag>
    </div>

    <!-- 过滤栏 -->
    <div class="audit-filters">
      <el-select v-model="filters.action" placeholder="动作" clearable size="small" style="width: 130px">
        <el-option v-for="a in actionOptions" :key="a.action" :value="a.action"
                   :label="`${actionLabel(a.action)} (${a.count})`" />
      </el-select>
      <el-select v-model="filters.result" placeholder="结果" clearable size="small" style="width: 110px">
        <el-option label="成功" value="success" />
        <el-option label="失败" value="fail" />
        <el-option label="预演" value="dry-run" />
      </el-select>
      <el-input v-model="filters.host" placeholder="主机 / 操作者 IP" clearable size="small"
                style="width: 170px" @keyup.enter="load(1)" />
      <el-input v-model="filters.keyword" placeholder="详情关键字" clearable size="small"
                style="width: 170px" @keyup.enter="load(1)" />
      <el-date-picker v-model="dateRange" type="daterange" size="small" start-placeholder="开始日期"
                      end-placeholder="结束日期" value-format="YYYY-MM-DD" style="width: 240px" />
      <el-button size="small" type="primary" :icon="Search" @click="load(1)">查询</el-button>
      <el-button size="small" :icon="Refresh" @click="reset">重置</el-button>
      <el-button size="small" type="success" :icon="Download" @click="exportCsv"
                 style="margin-left: auto">导出 CSV</el-button>
    </div>

    <!-- 表格 -->
    <el-table :data="items" v-loading="loading" size="small" stripe height="52vh"
              :row-key="r => r.time + r.action + r.host">
      <el-table-column prop="time" label="时间" width="150" />
      <el-table-column label="动作" width="110">
        <template #default="{ row }">
          <el-tag size="small" :type="actionTagType(row.action)" effect="light">
            {{ actionLabel(row.action) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="host" label="目标主机" width="130" show-overflow-tooltip />
      <el-table-column prop="deviceType" label="设备类型" width="95" />
      <el-table-column label="结果" width="85">
        <template #default="{ row }">
          <el-tag size="small" :type="row.result === 'success' ? 'success' : row.result === 'fail' ? 'danger' : 'warning'">
            {{ row.result }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="clientIp" label="操作者IP" width="120" />
      <el-table-column label="命令数" width="75">
        <template #default="{ row }">{{ row.commands ?? '-' }}</template>
      </el-table-column>
      <el-table-column prop="detail" label="详情" min-width="240" show-overflow-tooltip />
    </el-table>

    <!-- 分页 -->
    <div class="audit-pagination">
      <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total"
                     layout="total, prev, pager, next, sizes" :page-sizes="[20, 50, 100, 200]"
                     @current-change="load()" @size-change="load(1)" background />
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Refresh, Download } from '@element-plus/icons-vue'

const visible = ref(false)
const loading = ref(false)
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const actionOptions = ref([])
const dateRange = ref(null)
const statsDays = 7

const stats = reactive({ total: 0, fails: 0, byAction: [] })

const filters = reactive({ action: '', result: '', host: '', keyword: '' })

const ACTION_LABELS = {
  login: '登录', 'change-password': '改密', push: '配置下发', 'push-batch': '批量下发',
  rollback: '配置回滚', 'ping-test': '连通测试', state: '采集状态', inspect: '设备巡检',
  discover: '网络发现', api: 'API 调用'
}
const actionLabel = a => ACTION_LABELS[a] || a
const actionTagType = a => ({ push: 'primary', 'push-batch': 'primary', rollback: 'warning',
  login: 'info', 'change-password': 'info', discover: 'success' }[a] || 'info')

const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem('tct-token') || ''}` })

function queryParams() {
  return {
    action: filters.action, result: filters.result, host: filters.host,
    keyword: filters.keyword,
    start: dateRange.value?.[0] || '', end: dateRange.value?.[1] || ''
  }
}

async function load(p) {
  if (p) page.value = p
  loading.value = true
  try {
    const qs = new URLSearchParams({ ...queryParams(), page: page.value, pageSize: pageSize.value })
    const resp = await fetch(`/api/audit/query?${qs}`, { headers: authHeaders() })
    if (resp.status === 401) { ElMessage.warning('会话已过期, 请重新登录'); return }
    const body = await resp.json()
    if (body.status === 'success') {
      items.value = body.data.items
      total.value = body.data.total
    }
  } catch (e) {
    ElMessage.error('审计日志加载失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

async function loadMeta() {
  try {
    const [a, s] = await Promise.all([
      fetch('/api/audit/actions', { headers: authHeaders() }).then(r => r.json()),
      fetch('/api/audit/stats?days=7', { headers: authHeaders() }).then(r => r.json())
    ])
    if (a.status === 'success') actionOptions.value = a.data
    if (s.status === 'success') {
      stats.byAction = s.data.byAction
      stats.fails = s.data.fails
      stats.total = s.data.byAction.reduce((n, x) => n + x.count, 0)
    }
  } catch { /* 忽略, 不阻塞面板 */ }
}

async function exportCsv() {
  try {
    const qs = new URLSearchParams(queryParams())
    const resp = await fetch(`/api/audit/export?${qs}`, { headers: authHeaders() })
    if (!resp.ok) { ElMessage.error('导出失败'); return }
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `审计日志-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    ElMessage.error('导出失败: ' + e.message)
  }
}

function reset() {
  filters.action = ''; filters.result = ''; filters.host = ''; filters.keyword = ''
  dateRange.value = null
  load(1)
}

function open() {
  visible.value = true
  loadMeta()
  load(1)
}

defineExpose({ open })
</script>

<style scoped>
.audit-stats { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.audit-filters { display: flex; gap: 8px; margin-bottom: 10px; align-items: center; flex-wrap: wrap; }
.audit-pagination { display: flex; justify-content: flex-end; margin-top: 10px; }
</style>
