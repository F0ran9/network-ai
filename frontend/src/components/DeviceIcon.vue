<template>
  <svg width="36" height="36" viewBox="0 0 36 36" xmlns="http://www.w3.org/2000/svg">
    <!-- 路由器: NetEquip 实物图 -->
    <template v-if="type === 'router'">
      <foreignObject width="36" height="36"><img :src="images.router" class="real-img"></foreignObject>
    </template>
    <!-- 交换机: NetEquip 实物图 -->
    <template v-else-if="type === 'switch'">
      <foreignObject width="36" height="36"><img :src="images.switch" class="real-img"></foreignObject>
    </template>
    <!-- 防火墙: NetEquip 实物图 -->
    <template v-else-if="type === 'firewall'">
      <foreignObject width="36" height="36"><img :src="images.firewall" class="real-img"></foreignObject>
    </template>
    <!-- 无线AP: NetEquip 实物图 -->
    <template v-else-if="type === 'ap'">
      <foreignObject width="36" height="36"><img :src="images.ap" class="real-img"></foreignObject>
    </template>
    <!-- 服务器: NetEquip 实物图 -->
    <template v-else-if="type === 'server'">
      <foreignObject width="36" height="36"><img :src="images.server" class="real-img"></foreignObject>
    </template>
    <!-- 负载均衡: AI 生成实物图 -->
    <template v-else-if="type === 'lb'">
      <foreignObject width="36" height="36"><img :src="images.lb" class="real-img"></foreignObject>
    </template>
    <!-- SDWAN 路由器: AI 生成实物图 -->
    <template v-else-if="type === 'sdwan'">
      <foreignObject width="36" height="36"><img :src="images.sdwan" class="real-img"></foreignObject>
    </template>
    <!-- 上网行为管理: AI 生成实物图 -->
    <template v-else-if="type === 'behavior'">
      <foreignObject width="36" height="36"><img :src="images.behavior" class="real-img"></foreignObject>
    </template>
    <!-- 云 / Internet: 真云形 -->
    <template v-else-if="type === 'cloud'">
      <path d="M 9.5 27
               A 5.5 5.5 0 0 1 8.2 16.2
               A 8.5 8.5 0 0 1 24.5 13
               A 6.5 6.5 0 0 1 27 27
               Z"
            fill="#E3F2FD" stroke="#1565C0" stroke-width="1.6" stroke-linejoin="round"/>
    </template>
    <!-- PC -->
    <template v-else-if="type === 'pc'">
      <rect x="3" y="2" width="30" height="22" rx="3" fill="#263238"/>
      <rect x="6" y="5" width="24" height="16" rx="2" fill="#1565C0"/>
      <rect x="15" y="24" width="6" height="5" fill="#37474F" rx="0.5"/>
      <rect x="8" y="28" width="20" height="3" rx="1.5" fill="#37474F"/>
    </template>
    <!-- Server -->
    <template v-else-if="type === 'server'">
      <rect x="4" y="1" width="28" height="34" rx="3" fill="#424242" stroke="#212121" stroke-width="1.5"/>
      <rect x="8" y="6" width="20" height="5" rx="1" fill="#616161"/>
      <circle cx="24" cy="8.5" r="1.5" fill="#4CAF50"/>
      <rect x="8" y="14" width="20" height="5" rx="1" fill="#616161"/>
      <circle cx="24" cy="16.5" r="1.5" fill="#4CAF50"/>
      <rect x="8" y="22" width="20" height="5" rx="1" fill="#616161"/>
      <circle cx="24" cy="24.5" r="1.5" fill="#FFC107"/>
      <rect x="8" y="29" width="8" height="1.5" rx="0.5" fill="#757575"/>
      <rect x="18" y="29" width="8" height="1.5" rx="0.5" fill="#757575"/>
    </template>
    <!-- 无线控制器AC: eNSP 风格紫色机架 + 双排箭头 -->
    <template v-else-if="type === 'ac'">
      <rect x="1" y="8" width="34" height="20" rx="3" fill="#7E57C2" stroke="#4A148C" stroke-width="1.5"/>
      <g fill="#FFFFFF">
        <rect x="4.5" y="12.6" width="4.6" height="1.8"/><polygon points="9.1,11.6 11.5,13.5 9.1,15.4"/>
        <rect x="12.8" y="12.6" width="4.6" height="1.8"/><polygon points="17.4,11.6 19.8,13.5 17.4,15.4"/>
        <rect x="21.1" y="12.6" width="4.6" height="1.8"/><polygon points="25.7,11.6 28.1,13.5 25.7,15.4"/>
        <rect x="15.2" y="18.6" width="4.6" height="1.8"/><polygon points="15.2,16.6 12.8,18.5 15.2,20.4"/>
        <rect x="23.5" y="18.6" width="4.6" height="1.8"/><polygon points="23.5,16.6 21.1,18.5 23.5,20.4"/>
      </g>
      <circle cx="4.5" cy="24.6" r="1.1" fill="#4CAF50"/>
      <circle cx="8" cy="24.6" r="1.1" fill="#4CAF50"/>
      <circle cx="31" cy="24.6" r="1.1" fill="#FFC107"/>
    </template>
    <!-- Laptop -->
    <template v-else-if="type === 'laptop'">
      <rect x="4" y="4" width="28" height="20" rx="3" fill="#37474F" stroke="#000" stroke-width="1.5"/>
      <rect x="7" y="7" width="22" height="14" rx="2" fill="#1565C0"/>
      <rect x="1" y="24" width="34" height="5" rx="2" fill="#37474F" stroke="#263238" stroke-width="1"/>
    </template>
    <!-- IP Phone -->
    <template v-else-if="type === 'phone'">
      <rect x="6" y="3" width="24" height="30" rx="4" fill="#37474F" stroke="#000" stroke-width="1.5"/>
      <rect x="10" y="7" width="16" height="18" rx="2" fill="#E0E0E0" stroke="#BDBDBD" stroke-width="0.5"/>
      <circle cx="18" cy="28" r="2" fill="#78909C"/>
    </template>
    <!-- Camera -->
    <template v-else-if="type === 'camera'">
      <rect x="4" y="14" width="28" height="18" rx="2" fill="#ECEFF1" stroke="#37474F" stroke-width="1.5"/>
      <path d="M6 14 Q18 2 30 14" fill="#B0BEC5" stroke="#546E7A" stroke-width="1.5"/>
      <circle cx="18" cy="19" r="5" fill="#263238"/>
      <circle cx="18" cy="19" r="3" fill="#1565C0"/>
      <circle cx="18" cy="19" r="1.5" fill="#42A5F5"/>
      <rect x="4" y="12" width="3" height="4" fill="#546E7A" rx="0.5"/>
    </template>
    <!-- NVR -->
    <template v-else-if="type === 'nvr'">
      <rect x="2" y="4" width="32" height="28" rx="3" fill="#37474F" stroke="#212121" stroke-width="1.5"/>
      <rect x="6" y="8" width="24" height="4" rx="1" fill="#616161"/>
      <circle cx="26" cy="10" r="1" fill="#F44336"/>
      <rect x="6" y="15" width="24" height="4" rx="1" fill="#616161"/>
      <circle cx="26" cy="17" r="1" fill="#4CAF50"/>
      <rect x="6" y="22" width="24" height="4" rx="1" fill="#616161"/>
      <circle cx="26" cy="24" r="1" fill="#4CAF50"/>
      <rect x="12" y="28" width="12" height="2" rx="1" fill="#757575"/>
    </template>
    <!-- 傻瓜交换机: 同交换机画风, 浅色 -->
    <template v-else-if="type === 'dumb-switch'">
      <rect x="1" y="8" width="34" height="20" rx="3" fill="#78909C" stroke="#455A64" stroke-width="1.5"/>
      <g fill="#CFD8DC">
        <rect x="4.5" y="12.6" width="4.6" height="1.8"/><polygon points="9.1,11.6 11.5,13.5 9.1,15.4"/>
        <rect x="12.8" y="12.6" width="4.6" height="1.8"/><polygon points="17.4,11.6 19.8,13.5 17.4,15.4"/>
        <rect x="21.1" y="12.6" width="4.6" height="1.8"/><polygon points="25.7,11.6 28.1,13.5 25.7,15.4"/>
        <rect x="15.2" y="18.6" width="4.6" height="1.8"/><polygon points="15.2,16.6 12.8,18.5 15.2,20.4"/>
        <rect x="23.5" y="18.6" width="4.6" height="1.8"/><polygon points="23.5,16.6 21.1,18.5 23.5,20.4"/>
      </g>
      <text x="18" y="26" text-anchor="middle" fill="#ECEFF1" font-size="4.5" font-family="sans-serif">UNMANAGED</text>
    </template>
    <!-- Printer -->
    <template v-else-if="type === 'printer'">
      <rect x="3" y="6" width="30" height="18" rx="4" fill="#ECEFF1" stroke="#546E7A" stroke-width="1.5"/>
      <rect x="7" y="9" width="22" height="10" rx="2" fill="#B0BEC5"/>
      <rect x="10" y="12" width="16" height="5" fill="#FAFAFA"/>
      <rect x="2" y="24" width="32" height="4" rx="1.5" fill="#78909C"/>
      <rect x="20" y="30" width="8" height="3" rx="1" fill="#546E7A"/>
    </template>
    <!-- IPS: 紫色机架 + 盾形元素 -->
    <template v-else-if="type === 'ips'">
      <rect x="1" y="8" width="34" height="20" rx="3" fill="#8E24AA" stroke="#4A148C" stroke-width="1.5"/>
      <path d="M18 11 L24 13.5 L24 18.5 Q24 23 18 25.5 Q12 23 12 18.5 L12 13.5 Z"
            fill="#F3E5F5" stroke="#4A148C" stroke-width="1"/>
      <path d="M15 18.5 L17.3 21 L21.5 15.5" fill="none" stroke="#8E24AA" stroke-width="1.8"/>
    </template>
    <!-- Default fallback -->
    <template v-else>
      <rect x="4" y="6" width="28" height="24" rx="4" fill="#90A4AE" stroke="#546E7A" stroke-width="1.5"/>
    </template>
  </svg>
</template>

<script setup>
import routerImg from '../assets/netequip/icons/router.png'
import switchImg from '../assets/netequip/icons/switch-core.png'
import firewallImg from '../assets/netequip/icons/firewall.png'
import apImg from '../assets/netequip/icons/ap.png'
import serverImg from '../assets/netequip/icons/server.png'
import lbImg from '../assets/netequip/icons/lb.png'
import sdwanImg from '../assets/netequip/icons/sdwan.png'
import behaviorImg from '../assets/netequip/icons/behavior.png'

const images = { router: routerImg, switch: switchImg, firewall: firewallImg, ap: apImg, server: serverImg, lb: lbImg, sdwan: sdwanImg, behavior: behaviorImg }

defineProps({
  type: { type: String, required: true }
})
</script>

<style scoped>
.real-img {
  width: 36px;
  height: 36px;
  object-fit: contain;
  background: #fff;
  border: 1px solid #cfd8dc;
  border-radius: 3px;
}
</style>
