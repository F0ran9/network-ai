import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import axios from 'axios'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
// 设计令牌与基础层：必须在 Element Plus 样式之后引入以接管其变量
import './styles/tokens.css'
import './styles/base.css'
import App from './App.vue'

// ---- 鉴权: 所有请求自动附带会话 token; 401 时清除并回到登录页 ----
axios.interceptors.request.use((config) => {
  const token = localStorage.getItem('tct-token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})
axios.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && localStorage.getItem('tct-token')) {
      localStorage.removeItem('tct-token')
      window.location.reload() // 回到登录页
    }
    return Promise.reject(err)
  }
)

// Restore dark mode preference
const darkMode = localStorage.getItem('topo-dark-mode')
if (darkMode === 'true') {
  document.documentElement.classList.add('dark')
}

const app = createApp(App)
app.use(ElementPlus)
app.mount('#app')
