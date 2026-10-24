# 网络拓扑配置生成器

拖拽式网络拓扑设计与多厂商设备配置一键生成工具。支持 23 家主流网络设备厂商，覆盖交换机、路由器、防火墙的 CLI 配置自动生成。

## 功能特性

### 拓扑设计
- **拖拽绘制** — 从设备工具箱拖拽设备到画布，端口连线自动匹配
- **模板系统** — 内置中小型三层架构、园区网、等保合规、Spine-Leaf 等 5 种拓扑模板
- **拓扑图导入** — 支持从拓扑图片（JPG/PNG/BMP/WebP）AI 识别并自动生成拓扑
- **拓扑图导出** — 支持导出为 PNG 高清、JPEG、SVG 矢量图
- **自动布局** — 一键自动排列设备，采用层次化布局算法
- **导入/导出** — 拓扑文件 JSON 格式导入导出，支持版本管理

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
- **暗色模式** — 支持日间/夜间主题切换，偏好持久化

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
| POST | `/api/generate` | 生成设备配置 |
| POST | `/api/generate/kb` | 纯知识库生成配置（不使用 AI） |
| POST | `/api/analyze/topology-image` | 拓扑图视觉分析 |
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
