<template>
  <el-drawer
    :model-value="!!nodeData"
    @update:model-value="$emit('close')"
    title="设备属性"
    direction="rtl"
    size="340px"
    :close-on-click-modal="true"
    @closed="$emit('closed')"
  >
    <template v-if="nodeData">
      <el-form label-width="84px" size="default" @submit.prevent>
        <!-- ── 基本信息 ── -->
        <div class="section-title">基本信息</div>
        <el-form-item label="设备标签">
          <el-input v-model="form.label" placeholder="如 内网防火墙" />
        </el-form-item>
        <el-form-item label="设备类型">
          <el-select v-model="form.category" filterable style="width:100%" @change="onCategoryChange">
            <el-option v-for="c in CATEGORY_OPTIONS" :key="c.value" :label="c.label" :value="c.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="厂商">
          <el-select v-model="form.vendor" filterable allow-create default-first-option style="width:100%" placeholder="选择或输入厂商">
            <el-option v-for="v in VENDOR_OPTIONS" :key="v" :label="v" :value="v" />
          </el-select>
        </el-form-item>
        <el-form-item label="设备型号">
          <el-input v-model="form.model" placeholder="如 USG6000E / S5735-L24T4S-A" />
        </el-form-item>
        <el-form-item label="网络角色">
          <el-select v-model="form.role" style="width:100%" placeholder="在网络中的角色">
            <el-option v-for="r in ROLE_OPTIONS" :key="r.value" :label="r.label" :value="r.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="设备用途、承载业务等" />
        </el-form-item>

        <!-- ── 管理信息 ── -->
        <div class="section-title">管理信息</div>
        <el-form-item label="主机名">
          <el-input v-model="form.hostname" placeholder="配置生成使用的主机名" />
        </el-form-item>
        <el-form-item label="管理 IP">
          <el-input v-model="form.mgmtIp" placeholder="如 10.94.89.242/24" />
        </el-form-item>
        <el-form-item label="管理 VLAN">
          <el-input-number v-model="form.mgmtVlan" :min="1" :max="4094" placeholder="如 99" style="width:100%" />
        </el-form-item>
        <el-form-item label="软件版本">
          <el-input v-model="form.softwareVersion" placeholder="如 V500R005C20" />
        </el-form-item>

        <!-- ── 资产与运维 ── -->
        <div class="section-title">资产与运维</div>
        <el-form-item label="所在位置">
          <el-input v-model="form.location" placeholder="如 核心机房 A02 机柜" />
        </el-form-item>
        <el-form-item label="资产编号">
          <el-input v-model="form.assetTag" placeholder="固定资产标签号" />
        </el-form-item>
        <el-form-item label="序列号">
          <el-input v-model="form.serialNumber" placeholder="SN 条码号" />
        </el-form-item>
        <el-form-item label="设备状态">
          <el-select v-model="form.status" style="width:100%">
            <el-option v-for="s in STATUS_OPTIONS" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="维护人">
          <el-input v-model="form.owner" placeholder="负责人 / 联系方式" />
        </el-form-item>

        <el-divider />
        <div class="device-info">
          <span>内部ID：{{ nodeData.key || '—' }}</span>
        </div>

        <el-divider />
        <div class="form-actions">
          <el-button type="primary" @click="apply">应用</el-button>
          <el-button type="danger" plain @click="confirmDelete">删除设备</el-button>
        </div>
      </el-form>
    </template>
  </el-drawer>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'

const props = defineProps({
  nodeData: Object,
})

const emit = defineEmits(['close', 'closed', 'apply', 'delete'])

const CATEGORY_OPTIONS = [
  { value: 'router', label: '路由器' },
  { value: 'switch', label: '交换机' },
  { value: 'firewall', label: '防火墙' },
  { value: 'server', label: '服务器' },
  { value: 'ap', label: '无线AP' },
  { value: 'ac', label: '无线控制器 AC' },
  { value: 'lb', label: '负载均衡' },
  { value: 'sdwan', label: 'SDWAN 路由器' },
  { value: 'behavior', label: '上网行为管理' },
  { value: 'ips', label: '入侵防御 IPS' },
  { value: 'cloud', label: '运营商/外网' },
  { value: 'pc', label: '终端 PC' },
  { value: 'laptop', label: '笔记本' },
  { value: 'printer', label: '打印机' },
  { value: 'phone', label: 'IP话机' },
  { value: 'camera', label: '监控摄像头' },
  { value: 'nvr', label: '硬盘录像机 NVR' },
  { value: 'dumb-switch', label: '傻瓜交换机' },
]

const VENDOR_OPTIONS = ['Huawei', 'H3C', 'Cisco', 'Ruijie', 'Juniper', 'Sangfor', 'DPtech', '其他']

const ROLE_OPTIONS = [
  { value: 'core', label: '核心层' },
  { value: 'aggregation', label: '汇聚层' },
  { value: 'access', label: '接入层' },
  { value: 'router', label: '出口路由' },
  { value: 'security', label: '安全边界' },
  { value: 'wireless', label: '无线' },
  { value: 'endpoint', label: '终端' },
]

const STATUS_OPTIONS = [
  { value: 'planned', label: '规划中' },
  { value: 'deployed', label: '已部署' },
  { value: 'running', label: '运行中' },
  { value: 'maintenance', label: '维护中' },
  { value: 'retired', label: '已停用' },
]

const EMPTY_FORM = {
  label: '', hostname: '', mgmtIp: '', mgmtVlan: null, description: '',
  category: 'switch', vendor: '', model: '', role: '',
  softwareVersion: '', location: '', assetTag: '', serialNumber: '',
  status: 'planned', owner: '',
}

const form = ref({ ...EMPTY_FORM })

watch(() => props.nodeData, (data) => {
  if (data) {
    form.value = {
      ...EMPTY_FORM,
      label: data.label || '',
      hostname: data.hostname || '',
      mgmtIp: data.mgmtIp || '',
      mgmtVlan: data.mgmtVlan || null,
      description: data.description || '',
      category: data.category || 'switch',
      vendor: data.vendor || '',
      model: data.model || '',
      role: data.role || '',
      softwareVersion: data.softwareVersion || '',
      location: data.location || '',
      assetTag: data.assetTag || '',
      serialNumber: data.serialNumber || '',
      status: data.status || 'planned',
      owner: data.owner || '',
    }
  }
}, { immediate: true })

function onCategoryChange(cat) {
  // 类型切换时同步建议的角色，减少手工选择
  const map = {
    router: 'router', firewall: 'security', lb: 'router', sdwan: 'router',
    ap: 'wireless', ac: 'wireless', switch: 'access',
  }
  if (map[cat]) form.value.role = map[cat]
}

function apply() {
  emit('apply', { key: props.nodeData.key, ...form.value })
  ElMessage.success('设备属性已更新')
}

function confirmDelete() {
  ElMessageBox.confirm(
    `确定删除设备 "${props.nodeData?.label || props.nodeData?.key}" 及其所有连线？`,
    '确认删除',
    { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
  ).then(() => {
    emit('delete', props.nodeData.key)
    ElMessage.success('设备已删除')
  }).catch(() => {})
}
</script>

<style scoped>
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: #409eff;
  margin: 4px 0 12px;
  padding-left: 8px;
  border-left: 3px solid #409eff;
  line-height: 1.1;
}
.section-title:not(:first-child) {
  margin-top: 18px;
}
.device-info {
  font-size: 12px;
  color: #909399;
}
.form-actions {
  display: flex;
  justify-content: space-between;
}
</style>
