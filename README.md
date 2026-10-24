# 网络拓扑配置生成器

拖拽式网络拓扑设计与多厂商设备配置一键生成工具。支持 23 家主流网络设备厂商，覆盖交换机、路由器、防火墙的 CLI 配置自动生成。

## 界面预览

**拓扑编辑器** — eNSP 风格实物图标、IP 旁标、链路属性标注、可折叠双面板：

![拓扑编辑器](docs/screenshots/editor.png)

**登录页**（首次启动自动生成随机密码）：

![登录页](docs/screenshots/login.png)

**设备属性编辑** — 单击设备即可编辑型号、厂商、管理 IP、资产信息等 15 项属性：

![设备属性](docs/screenshots/device-properties.png)

**全局设置** — NTP/SNMP/AAA/DNS 参数与平台登录密码修改：

![全局设置](docs/screenshots/settings.png)

**网络自动发现** — SSH+LLDP/CDP 扫描现网，扫描完成后按层级渲染拓扑预览图（含设备类别配色 / 管理 IP / SSH 失败标记），确认后一键生成拓扑与诊断报告：

![网络自动发现](docs/screenshots/network-discover.png)

**AI 助手** — 基于当前拓扑上下文的智能问答：

![AI 助手](docs/screenshots/ai-assistant.png)

## 功能特性

### 拓扑设计
- **网络自动发现** — 填入种子设备 SSH 账号，通过 LLDP/CDP 邻居表 BFS 递归扫描整网（华为/H3C/思科/锐捷），扫描完成后弹窗内直接渲染**拓扑预览图**（按核心/汇聚/接入层级自动排布，设备按类别配色，SSH 采集失败节点红框标记），并输出诊断报告（SSH 不可达 / 单链路风险 / 命名冲突 / LLDP 配置缺陷等），一键应用到画布
- **拖拽绘制** — 从设备工具箱拖拽设备到画布，端口连线自动匹配
- **模板系统** — 内置中小型三层架构、园区网、等保合规、Spine-Leaf 等 5 种拓扑模板
- **拓扑图导入** — 支持从拓扑图片（JPG/PNG/BMP/WebP）AI 识别并自动生成拓扑，自动识别设备类型、管理 IP、链路属性与业务分区
- **拓扑图导出** — 支持导出为 PNG 高清、JPEG、SVG 矢量图，自动合成图例卡片
- **自动布局** — 一键自动排列设备，采用层次化布局算法，自动生成安全域分区框
- **导入/导出** — 拓扑文件 JSON 格式导入导出，支持版本管理
- **可折叠面板** — 左侧设备库、右侧配置面板均可一键收起/展开

### 配置生成
- **多厂商支持** — Huawei、Cisco、H3C、Juniper、Arista、HPE、Ruijie、ZTE、Extreme、Dell、Sonic、Maipu、Hikvision、Tplink、Fiberhome、Dptecn、Inspur、Boda、Raisecom、Dcn、NSFocus、Sangfor、QiAnXin
- **一键生成** — 基于拓扑结构和厂商模板引擎，自动生成完整设备配置
- **子网规划** — 自动 VLAN 子网规划与 IP 分配
- **高级协议** — 支持 OSPF 动态路由、VRRP 冗余热备、ACL 访问控制策略自动生成
- **全局设置** — NTP 服务器、SNMP 共同体、AAA 管理账户、DNS 域名等全局参数统一配置

### 查看与导出
- **配置面板** — 按设备分块展示，支持复制、差异对比、历史版本回溯
- **导出格式** — 单文件 .txt / 每设备独立 .cfg / Zip 压缩包（含 topology.json）
- **CLI 终端** — 内置设备命令行模拟器，可直接在设备上执行命令并回写配置

### 辅助功能
- **知识库** — 多厂商命令参考手册
- **AI 助手** — 基于拓扑上下文的智能问答
- **分析报告** — 拓扑校验告警与安全建议
- **设备台账** — 每台设备 15 项属性（型号/厂商/管理 IP/序列号/位置/维护人等）可视化编辑
- **暗色模式** — 支持日间/夜间主题切换，偏好持久化

## 登录与密码

平台采用**单密码登录**，所有 `/api` 接口需要会话 token：

- **首次启动**：若 `backend/.env` 中没有 `APP_PASSWORD`，后端自动生成 12 位随机密码，**打印在后端启动日志中**并写入 `backend/.env`
- **修改密码**：登录后打开【设置 → 全局参数设置 → 平台登录密码】，输入原密码与新密码即可（新密码至少 8 位，写回 `.env`，当前会话不受影响）
- 代码中不保存任何硬编码密码；`.env` 已被 `.gitignore` 排除，不会提交到仓库

## 技术架构

```
topology-config-tool/
├── backend/
│   ├── main.py                 # FastAPI 入口，API 路由
│   ├── kb_engine.py            # 多厂商知识库模板引擎（23 厂商命令语法）
│   ├── config_generator.py     # AI 配置生成（DeepSeek API）
│   ├── vision_analyzer.py      # 拓扑图视觉分析（Qwen-VL / DashScope）
│   ├── chat.py                 # AI 对话
│   ├── prompts.py              # Prompt 模板
│   ├── knowledge_base/         # 厂商命令模板库（20 个 JSON）
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.vue             # 主应用（布局、工具栏、状态管理）
│   │   ├── main.js             # Vue 入口
│   │   ├── components/         # 11 个核心组件
│   │   ├── topology/           # 拓扑逻辑（设备定义、连线规则、模板工厂等）
│   │   └── utils/              # 工具函数（diff 算法等）
│   ├── package.json
│   └── vite.config.js
├── .env.example                # 环境变量模板
├── .gitignore
├── setup.bat                   # 一键安装+启动（推荐）
├── start.bat                   # 快速启动（跳过安装步骤）
├── restart.bat                 # 重新构建前端并重启后端
└── build.bat                   # 仅构建前端
```

**前端**：Vue 3 (Composition API) + Vite + Element Plus + GoJS 2.3  
**后端**：FastAPI + DeepSeek API + DashScope Qwen-VL  
**运行端口**：`http://localhost:5732`

## 快速开始

### 环境要求
- Python 3.8+
- Node.js 18+
- DeepSeek API Key（必需）
- DashScope API Key（可选，拓扑图识别功能需要）

### 1. 克隆项目

```bash
git clone <repo-url>
cd topology-config-tool
```

### 2. 配置 API Key

```bash
cp .env.example backend/.env
# 编辑 backend/.env，填入你的 API Key
```

```env
DEEPSEEK_API_KEY=sk-your-deepseek-key-here

# 可选：拓扑图图片识别
DASHSCOPE_API_KEY=sk-your-dashscope-key-here
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
VISION_PROVIDER=dashscope
VISION_MODEL=qwen-vl-max
```

### 3. 安装依赖

**后端**：
```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
```

**前端**：
```bash
cd frontend
npm install
```

### 4. 启动服务

**方式一：一键启动（推荐）**
```
双击 setup.bat
```
自动完成：创建虚拟环境 → 安装依赖 → 检查配置 → 构建前端 → 启动服务

**方式二：手动启动**
```bash
# 终端 1 — 前端构建 + 后端
cd frontend && npm run build && cd ../backend && python main.py

# 终端 2 — 前端开发模式（可选，热更新）
cd frontend && npm run dev
```

### 5. 访问

浏览器打开 `http://localhost:5732`

> **首次启动的登录密码**在后端启动日志中打印（形如 `首次启动已生成随机登录密码: xxx`），也可查看 `backend/.env` 中的 `APP_PASSWORD`；登录后可在【设置 → 全局参数设置】中修改。

## 使用指南

### 基本流程
1. 从左侧设备工具箱拖拽设备到画布（可按厂商筛选）
2. 鼠标悬浮设备端口，拖拽到另一设备端口完成连线
3. 右键链路可配置 VLAN、Eth-Trunk 等参数
4. 选择目标厂商，点击「一键生成全部配置」
5. 右侧面板查看、复制或导出配置

### 工具栏说明
| 按钮 | 功能 |
|------|------|
| 保存 | 导出拓扑为 JSON 文件 |
| 加载 | 从 JSON 文件导入拓扑 |
| 导出图片 | 导出画布为 PNG / JPEG / SVG |
| 导入拓扑图 | 从图片 AI 识别拓扑结构 |
| 清空 | 清空画布 |
| 全局设置 | NTP、SNMP、AAA 等全局参数 |
| 新建模板 | 从预设模板快速创建拓扑 |
| 自动布局 | 自动排列设备位置 |
| 暗色模式 | 切换日间/夜间主题 |

### 右键菜单
- **设备**：打开命令行、编辑属性、复制设备、导出配置、删除
- **链路**：编辑 VLAN/端口配置、删除
- **画布**：粘贴设备、导出为图片、清空

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 平台登录，返回会话 token |
| POST | `/api/auth/change-password` | 修改平台登录密码（需登录） |
| GET | `/api/settings` | 获取全局设置 |
| POST | `/api/generate` | 生成设备配置 |
| POST | `/api/generate/kb` | 纯知识库生成配置（不使用 AI） |
| POST | `/api/analyze/topology-image` | 拓扑图视觉分析 |
| POST | `/api/discover/stream` | 网络自动发现（SSE 进度流，LLDP/CDP 递归扫描） |
| POST | `/api/chat` | AI 助手对话 |

## 支持的配置命令类型

- **基础**：hostname、VLAN 创建与命名、access/trunk 端口
- **路由**：静态路由、OSPF 动态路由
- **冗余**：VRRP 热备、Eth-Trunk 链路聚合
- **安全**：ACL 访问控制、管理 ACL
- **管理**：NTP、SNMP、AAA、SSH/Telnet
- **其他**：DHCP、端口镜像、生成树、LLDP

## License

MIT
