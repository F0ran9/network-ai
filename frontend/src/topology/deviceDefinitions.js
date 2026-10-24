export const deviceCategories = [
  {
    name: '上网路由器',
    expanded: true,
    models: [
      { type: 'router', category: 'router', role: 'router', model: 'AR1220', label: '华为 AR1220 上网路由器', vendor: 'Huawei', hostname: 'EdgeRouter' },
      { type: 'router', category: 'router', role: 'router', model: 'AR2240', label: '华为 AR2240 上网路由器', vendor: 'Huawei', hostname: 'EdgeRouter' },
      { type: 'router', category: 'router', role: 'router', model: 'AR3260', label: '华为 AR3260 上网路由器', vendor: 'Huawei', hostname: 'EdgeRouter' },
      { type: 'router', category: 'router', role: 'router', model: 'NE40E', label: '华为 NE40E 核心路由器', vendor: 'Huawei', hostname: 'EdgeRouter' },
      { type: 'router', category: 'router', role: 'router', model: 'MSR2600', label: 'H3C MSR2600 上网路由器', vendor: 'H3C', hostname: 'EdgeRouter' },
      { type: 'router', category: 'router', role: 'router', model: 'MSR3600', label: 'H3C MSR3600 上网路由器', vendor: 'H3C', hostname: 'EdgeRouter' },
      { type: 'router', category: 'router', role: 'router', model: 'ISR4321', label: '思科 ISR4321 上网路由器', vendor: 'Cisco', hostname: 'EdgeRouter' },
      { type: 'router', category: 'router', role: 'router', model: 'ISR4451', label: '思科 ISR4451 上网路由器', vendor: 'Cisco', hostname: 'EdgeRouter' },
      { type: 'router', category: 'router', role: 'router', model: 'RSR30-X', label: '锐捷 RSR30-X 上网路由器', vendor: 'Ruijie', hostname: 'EdgeRouter' },
    ]
  },
  {
    name: '核心交换机',
    expanded: true,
    models: [
      { type: 'switch', category: 'switch', role: 'core', model: 'S7700', label: '华为 S7700 核心交换机', vendor: 'Huawei', hostname: 'CoreSW' },
      { type: 'switch', category: 'switch', role: 'core', model: 'S9700', label: '华为 S9700 核心交换机', vendor: 'Huawei', hostname: 'CoreSW' },
      { type: 'switch', category: 'switch', role: 'core', model: 'S12700', label: '华为 S12700 核心交换机', vendor: 'Huawei', hostname: 'CoreSW' },
      { type: 'switch', category: 'switch', role: 'core', model: 'CE12800', label: '华为 CE12800 数据中心交换机', vendor: 'Huawei', hostname: 'CoreSW' },
      { type: 'switch', category: 'switch', role: 'core', model: 'S7500', label: 'H3C S7500 核心交换机', vendor: 'H3C', hostname: 'CoreSW' },
      { type: 'switch', category: 'switch', role: 'core', model: 'S10500', label: 'H3C S10500 核心交换机', vendor: 'H3C', hostname: 'CoreSW' },
      { type: 'switch', category: 'switch', role: 'core', model: 'C9500', label: '思科 C9500 核心交换机', vendor: 'Cisco', hostname: 'CoreSW' },
      { type: 'switch', category: 'switch', role: 'core', model: 'RG-S8610', label: '锐捷 RG-S8610 核心交换机', vendor: 'Ruijie', hostname: 'CoreSW' },
      { type: 'switch', category: 'switch', role: 'core', model: 'S6800', label: '迈普 S6800 核心交换机', vendor: 'Maipu', hostname: 'CoreSW' },
    ]
  },
  {
    name: '汇聚交换机',
    expanded: true,
    models: [
      { type: 'switch', category: 'switch', role: 'aggregation', model: 'S6700', label: '华为 S6700 汇聚交换机', vendor: 'Huawei', hostname: 'AggSW' },
      { type: 'switch', category: 'switch', role: 'aggregation', model: 'S5700', label: '华为 S5700 汇聚交换机', vendor: 'Huawei', hostname: 'AggSW' },
      { type: 'switch', category: 'switch', role: 'aggregation', model: 'S5500', label: 'H3C S5500 汇聚交换机', vendor: 'H3C', hostname: 'AggSW' },
      { type: 'switch', category: 'switch', role: 'aggregation', model: 'S5560', label: 'H3C S5560 汇聚交换机', vendor: 'H3C', hostname: 'AggSW' },
      { type: 'switch', category: 'switch', role: 'aggregation', model: 'C9300', label: '思科 C9300 汇聚交换机', vendor: 'Cisco', hostname: 'AggSW' },
      { type: 'switch', category: 'switch', role: 'aggregation', model: 'RG-S5750', label: '锐捷 RG-S5750 汇聚交换机', vendor: 'Ruijie', hostname: 'AggSW' },
      { type: 'switch', category: 'switch', role: 'aggregation', model: 'S5800', label: '烽火 S5800 汇聚交换机', vendor: 'Fiberhome', hostname: 'AggSW' },
      { type: 'switch', category: 'switch', role: 'aggregation', model: 'LSW6600', label: '迪普 LSW6600 汇聚交换机', vendor: 'Dptecn', hostname: 'AggSW' },
    ]
  },
  {
    name: '接入交换机',
    expanded: true,
    models: [
      { type: 'switch', category: 'switch', role: 'access', model: 'S3700', label: '华为 S3700 接入交换机', vendor: 'Huawei', hostname: 'AccSW' },
      { type: 'switch', category: 'switch', role: 'access', model: 'S2700', label: '华为 S2700 接入交换机', vendor: 'Huawei', hostname: 'AccSW' },
      { type: 'switch', category: 'switch', role: 'access', model: 'S5120', label: 'H3C S5120 接入交换机', vendor: 'H3C', hostname: 'AccSW' },
      { type: 'switch', category: 'switch', role: 'access', model: 'S6520', label: 'H3C S6520 接入交换机', vendor: 'H3C', hostname: 'AccSW' },
      { type: 'switch', category: 'switch', role: 'access', model: 'C2960', label: '思科 C2960 接入交换机', vendor: 'Cisco', hostname: 'AccSW' },
      { type: 'switch', category: 'switch', role: 'access', model: 'C3850', label: '思科 C3850 接入交换机', vendor: 'Cisco', hostname: 'AccSW' },
      { type: 'switch', category: 'switch', role: 'access', model: 'RG-S2928', label: '锐捷 RG-S2928 接入交换机', vendor: 'Ruijie', hostname: 'AccSW' },
      { type: 'switch', category: 'switch', role: 'access', model: 'RG-S2952', label: '锐捷 RG-S2952 接入交换机', vendor: 'Ruijie', hostname: 'AccSW' },
      { type: 'switch', category: 'switch', role: 'access', model: 'S3200', label: '迈普 S3200 接入交换机', vendor: 'Maipu', hostname: 'AccSW' },
      { type: 'switch', category: 'switch', role: 'access', model: 'DS-3E1526', label: '海康 DS-3E1526 接入交换机', vendor: 'Hikvision', hostname: 'AccSW' },
      { type: 'switch', category: 'switch', role: 'access', model: 'TL-SG3428', label: 'TP-LINK SG3428 接入交换机', vendor: 'TP-LINK', hostname: 'AccSW' },
      { type: 'switch', category: 'switch', role: 'access', model: 'S2200', label: '烽火 S2200 接入交换机', vendor: 'Fiberhome', hostname: 'AccSW' },
      { type: 'switch', category: 'switch', role: 'access', model: 'LSW3600', label: '迪普 LSW3600 接入交换机', vendor: 'Dptecn', hostname: 'AccSW' },
      { type: 'switch', category: 'switch', role: 'access', model: 'ISCOM2600', label: '瑞斯康达 ISCOM2600 接入交换机', vendor: 'Raisecom', hostname: 'AccSW' },
      { type: 'switch', category: 'switch', role: 'access', model: 'DCS-3950', label: '神州数码 DCS-3950 接入交换机', vendor: 'Dcn', hostname: 'AccSW' },
    ]
  },
  {
    name: '安全设备',
    expanded: true,
    models: [
      // 华为防火墙
      { type: 'firewall', category: 'firewall', role: 'security', model: 'USG6000', label: '华为 USG6000 防火墙', vendor: 'Huawei', hostname: 'FW' },
      { type: 'firewall', category: 'firewall', role: 'security', model: 'USG6500', label: '华为 USG6500 防火墙', vendor: 'Huawei', hostname: 'FW' },
      { type: 'firewall', category: 'firewall', role: 'security', model: 'USG6600', label: '华为 USG6600 防火墙', vendor: 'Huawei', hostname: 'FW' },
      // H3C防火墙
      { type: 'firewall', category: 'firewall', role: 'security', model: 'SecPath F1000', label: 'H3C SecPath F1000 防火墙', vendor: 'H3C', hostname: 'FW' },
      { type: 'firewall', category: 'firewall', role: 'security', model: 'SecPath F5000', label: 'H3C SecPath F5000 防火墙', vendor: 'H3C', hostname: 'FW' },
      // 绿盟安全
      { type: 'firewall', category: 'firewall', role: 'security', model: 'NF-NX3-G4120', label: '绿盟 NF-NX3 防火墙', vendor: 'NSFocus', hostname: 'NSFocus-FW' },
      { type: 'firewall', category: 'firewall', role: 'security', model: 'NF-NX5-G8180', label: '绿盟 NF-NX5 防火墙', vendor: 'NSFocus', hostname: 'NSFocus-FW' },
      { type: 'ips', category: 'firewall', role: 'security', model: 'NIPS-6000', label: '绿盟 NIPS-6000 入侵防御', vendor: 'NSFocus', hostname: 'NSFocus-IPS' },
      { type: 'ips', category: 'firewall', role: 'security', model: 'NIPS-8000', label: '绿盟 NIPS-8000 入侵防御', vendor: 'NSFocus', hostname: 'NSFocus-IPS' },
      // 深信服
      { type: 'firewall', category: 'firewall', role: 'security', model: 'AF-1000', label: '深信服 AF-1000 下一代防火墙', vendor: 'Sangfor', hostname: 'Sangfor-FW' },
      { type: 'firewall', category: 'firewall', role: 'security', model: 'AF-2000', label: '深信服 AF-2000 下一代防火墙', vendor: 'Sangfor', hostname: 'Sangfor-FW' },
      { type: 'firewall', category: 'firewall', role: 'security', model: 'AC-1000', label: '深信服 AC-1000 上网行为管理', vendor: 'Sangfor', hostname: 'Sangfor-AC' },
      // 奇安信
      { type: 'firewall', category: 'firewall', role: 'security', model: 'NSG3000', label: '奇安信 NSG3000 防火墙', vendor: 'QiAnXin', hostname: 'QiAnXin-FW' },
      { type: 'firewall', category: 'firewall', role: 'security', model: 'NSG7000', label: '奇安信 NSG7000 防火墙', vendor: 'QiAnXin', hostname: 'QiAnXin-FW' },
      // 思科安全
      { type: 'firewall', category: 'firewall', role: 'security', model: 'Firepower 2100', label: '思科 Firepower 2100 防火墙', vendor: 'Cisco', hostname: 'Cisco-FW' },
    ]
  },
  {
    name: '终端设备',
    expanded: true,
    models: [
      // VLAN-tagged PCs
      { type: 'pc', category: 'terminal', role: 'endpoint', model: 'PC-VLAN10', label: 'VLAN10 办公电脑', vendor: 'Generic', hostname: 'VLAN10-PC', vlan: 10, description: '业务终端-VLAN10' },
      { type: 'pc', category: 'terminal', role: 'endpoint', model: 'PC-VLAN20', label: 'VLAN20 办公电脑', vendor: 'Generic', hostname: 'VLAN20-PC', vlan: 20, description: '业务终端-VLAN20' },
      { type: 'pc', category: 'terminal', role: 'endpoint', model: 'PC-VLAN30', label: 'VLAN30 办公电脑', vendor: 'Generic', hostname: 'VLAN30-PC', vlan: 30, description: '业务终端-VLAN30' },
      { type: 'pc', category: 'terminal', role: 'endpoint', model: 'PC-VLAN254', label: 'VLAN254 网管电脑', vendor: 'Generic', hostname: 'VLAN254-MGMT', vlan: 254, description: '网管终端' },
      // Surveillance
      { type: 'camera', category: 'terminal', role: 'endpoint', model: 'Camera-VLAN40', label: 'VLAN40 监控摄像机', vendor: 'Generic', hostname: 'Camera-01', vlan: 40, description: '监控摄像机' },
      { type: 'nvr', category: 'terminal', role: 'endpoint', model: 'NVR-VLAN40', label: 'VLAN40 硬盘录像机', vendor: 'Generic', hostname: 'NVR-01', vlan: 40, description: '网络硬盘录像机' },
      // Server
      { type: 'server', category: 'terminal', role: 'endpoint', model: 'Server-VLAN100', label: 'VLAN100 业务服务器', vendor: 'Generic', hostname: 'Server-01', vlan: 100, description: '业务服务器' },
      // Generic endpoints (no VLAN)
      { type: 'pc', category: 'terminal', role: 'endpoint', model: 'PC', label: '通用PC', vendor: 'Generic', hostname: 'PC' },
      { type: 'laptop', category: 'terminal', role: 'endpoint', model: 'Laptop', label: '笔记本电脑', vendor: 'Generic', hostname: 'Laptop' },
      { type: 'server', category: 'terminal', role: 'endpoint', model: 'Server', label: '通用服务器', vendor: 'Generic', hostname: 'Server' },
      { type: 'phone', category: 'terminal', role: 'endpoint', model: 'IP-Phone', label: 'IP电话', vendor: 'Generic', hostname: 'Phone' },
      { type: 'printer', category: 'terminal', role: 'endpoint', model: 'Printer', label: '网络打印机', vendor: 'Generic', hostname: 'Printer' },
    ]
  },
  {
    name: '出口与流量设备',
    expanded: true,
    models: [
      { type: 'lb', category: 'lb', role: 'router', model: 'BIGIP-VE', label: '负载均衡器', vendor: 'Generic', hostname: 'LB' },
      { type: 'lb', category: 'lb', role: 'router', model: 'AD-1000', label: '深信服 AD 应用交付', vendor: 'Sangfor', hostname: 'LB' },
      { type: 'sdwan', category: 'sdwan', role: 'router', model: 'SDWAN-Edge', label: 'SDWAN 路由器', vendor: 'Generic', hostname: 'SDWAN' },
      { type: 'behavior', category: 'behavior', role: 'security', model: 'AC-1000-BM', label: '上网行为管理', vendor: 'Generic', hostname: 'BM' },
      { type: 'behavior', category: 'behavior', role: 'security', model: 'AC-6000-BM', label: '深信服 AC-6000 行为管理', vendor: 'Sangfor', hostname: 'BM' },
    ]
  },
  {
    name: '常用图标',
    expanded: false,
    models: [
      { type: 'cloud', category: 'other', role: 'cloud', model: 'Cloud', label: '云/Internet', vendor: 'Generic', hostname: 'Internet' },
      { type: 'dumb-switch', category: 'other', role: 'endpoint', model: 'DumbSW', label: '傻瓜交换机', vendor: 'Generic', hostname: 'DumbSW' },
      { type: 'ap', category: 'wireless', role: 'access-point', model: 'AP-Generic', label: '无线AP', vendor: 'Generic', hostname: 'AP' },
    ]
  },
  {
    name: '无线设备',
    expanded: false,
    models: [
      { type: 'ap', category: 'wireless', role: 'access-point', model: 'AP6050DN', label: '华为 AP6050DN 无线AP', vendor: 'Huawei', hostname: 'AP' },
      { type: 'ap', category: 'wireless', role: 'access-point', model: 'AP7050DN', label: '华为 AP7050DN 无线AP', vendor: 'Huawei', hostname: 'AP' },
      { type: 'ap', category: 'wireless', role: 'access-point', model: 'WA6638', label: 'H3C WA6638 无线AP', vendor: 'H3C', hostname: 'AP' },
      { type: 'ac', category: 'wireless', role: 'controller', model: 'AC6005', label: '华为 AC6005 无线控制器', vendor: 'Huawei', hostname: 'AC' },
      { type: 'ac', category: 'wireless', role: 'controller', model: 'AC6605', label: '华为 AC6605 无线控制器', vendor: 'Huawei', hostname: 'AC' },
      { type: 'ac', category: 'wireless', role: 'controller', model: 'WX5540H', label: 'H3C WX5540H 无线控制器', vendor: 'H3C', hostname: 'AC' },
    ]
  },
]
