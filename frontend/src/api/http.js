import axios from "axios"

const http = axios.create({
  baseURL: window.location.origin,  // works for both dev (localhost:16888) and packaged Electron app
  timeout: 30000,
  withCredentials: true,
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem("vm_token")
  if (token && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem("vm_token")
      localStorage.removeItem("vm_username")
      if (window.location.pathname !== "/login") {
        window.location.href = "/login"
      }
    }
    console.error("API error:", err.response?.data || err.message)
    return Promise.reject(err)
  }
)

export default http
