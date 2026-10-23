import { useState, useEffect } from "react"
import { useNavigate, useLocation } from "react-router-dom"
import {
  Box,
  Card,
  CardContent,
  Typography,
  TextField,
  Button,
  Alert,
  CircularProgress,
  InputAdornment,
  IconButton,
  Stack,
  Chip,
} from "@mui/material"
import LockOutlinedIcon from "@mui/icons-material/LockOutlined"
import PersonOutlineIcon from "@mui/icons-material/PersonOutline"
import Visibility from "@mui/icons-material/Visibility"
import VisibilityOff from "@mui/icons-material/VisibilityOff"
import SecurityIcon from "@mui/icons-material/SecurityOutlined"
import http from "../api/http"

export default function Login() {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const navigate = useNavigate()
  const location = useLocation()

  const from = location.state?.from?.pathname || "/"

  // Redirect to home if already logged in
  useEffect(() => {
    http.get("/api/auth/me").then(({ data }) => {
      if (!data.auth_enabled || data.authenticated) {
        navigate("/", { replace: true })
      }
    }).catch(() => {})
  }, [navigate])

  const handleLogin = async (e) => {
    e.preventDefault()
    if (!username.trim() || !password) {
      setError("Masukkan username dan password")
      return
    }

    setLoading(true)
    setError("")

    try {
      const { data } = await http.post("/api/auth/login", {
        username: username.trim(),
        password,
      })

      if (data.token) {
        localStorage.setItem("vm_token", data.token)
        localStorage.setItem("vm_username", data.username || username.trim())
      }

      navigate(from, { replace: true })
    } catch (err) {
      const detail = err.response?.data?.detail || "Login gagal. Periksa username dan password Anda."
      setError(detail)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        bgcolor: "#090d16",
        backgroundImage: `
          radial-gradient(at 0% 0%, rgba(13, 159, 110, 0.15) 0px, transparent 50%),
          radial-gradient(at 100% 100%, rgba(16, 185, 129, 0.1) 0px, transparent 50%),
          radial-gradient(at 50% 50%, rgba(15, 23, 42, 0.8) 0px, transparent 100%)
        `,
        p: 2,
      }}
    >
      <Card
        elevation={0}
        sx={{
          maxWidth: 420,
          width: "100%",
          borderRadius: 3.5,
          bgcolor: "rgba(17, 24, 39, 0.75)",
          backdropFilter: "blur(20px)",
          border: "1px solid rgba(255, 255, 255, 0.08)",
          boxShadow: "0 20px 40px -15px rgba(0, 0, 0, 0.6)",
        }}
      >
        <CardContent sx={{ p: { xs: 3, sm: 4.5 } }}>
          {/* Logo & Header */}
          <Stack alignItems="center" spacing={1} sx={{ mb: 3.5, textAlign: "center" }}>
            <Box
              sx={{
                width: 52,
                height: 52,
                borderRadius: 2.5,
                bgcolor: "rgba(13, 159, 110, 0.15)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                border: "1px solid rgba(13, 159, 110, 0.3)",
                mb: 0.5,
              }}
            >
              <SecurityIcon sx={{ fontSize: 28, color: "#10b981" }} />
            </Box>
            <Typography variant="h5" sx={{ fontWeight: 800, letterSpacing: "-0.02em", color: "#f8fafc" }}>
              ViralMint
            </Typography>
            <Typography variant="body2" sx={{ color: "#94a3b8", fontSize: "0.875rem" }}>
              Single-User Private Workspace
            </Typography>
            <Chip
              size="small"
              label="Secure Instance"
              sx={{
                bgcolor: "rgba(16, 185, 129, 0.1)",
                color: "#34d399",
                border: "1px solid rgba(16, 185, 129, 0.2)",
                fontSize: "0.72rem",
                fontWeight: 600,
                height: 22,
                mt: 0.5,
              }}
            />
          </Stack>

          {error && (
            <Alert
              severity="error"
              variant="outlined"
              sx={{
                mb: 2.5,
                borderRadius: 2,
                borderColor: "rgba(239, 68, 68, 0.3)",
                bgcolor: "rgba(239, 68, 68, 0.08)",
                color: "#fca5a5",
                "& .MuiAlert-icon": { color: "#ef4444" },
              }}
            >
              {error}
            </Alert>
          )}

          {/* Login Form */}
          <Box component="form" onSubmit={handleLogin}>
            <Stack spacing={2.2}>
              <Box>
                <Typography variant="caption" sx={{ color: "#cbd5e1", fontWeight: 600, mb: 0.75, display: "block" }}>
                  Username
                </Typography>
                <TextField
                  fullWidth
                  size="small"
                  placeholder="admin"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  disabled={loading}
                  autoComplete="username"
                  autoFocus
                  InputProps={{
                    startAdornment: (
                      <InputAdornment position="start">
                        <PersonOutlineIcon sx={{ color: "#64748b", fontSize: 20 }} />
                      </InputAdornment>
                    ),
                  }}
                  sx={{
                    "& .MuiOutlinedInput-root": {
                      bgcolor: "rgba(15, 23, 42, 0.6)",
                      borderRadius: 2,
                      color: "#f8fafc",
                      "& fieldset": { borderColor: "rgba(255, 255, 255, 0.1)" },
                      "&:hover fieldset": { borderColor: "rgba(255, 255, 255, 0.2)" },
                      "&.Mui-focused fieldset": { borderColor: "#10b981" },
                    },
                  }}
                />
              </Box>

              <Box>
                <Typography variant="caption" sx={{ color: "#cbd5e1", fontWeight: 600, mb: 0.75, display: "block" }}>
                  Password
                </Typography>
                <TextField
                  fullWidth
                  size="small"
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={loading}
                  autoComplete="current-password"
                  InputProps={{
                    startAdornment: (
                      <InputAdornment position="start">
                        <LockOutlinedIcon sx={{ color: "#64748b", fontSize: 20 }} />
                      </InputAdornment>
                    ),
                    endAdornment: (
                      <InputAdornment position="end">
                        <IconButton
                          size="small"
                          onClick={() => setShowPassword(!showPassword)}
                          edge="end"
                          sx={{ color: "#64748b" }}
                        >
                          {showPassword ? <VisibilityOff sx={{ fontSize: 18 }} /> : <Visibility sx={{ fontSize: 18 }} />}
                        </IconButton>
                      </InputAdornment>
                    ),
                  }}
                  sx={{
                    "& .MuiOutlinedInput-root": {
                      bgcolor: "rgba(15, 23, 42, 0.6)",
                      borderRadius: 2,
                      color: "#f8fafc",
                      "& fieldset": { borderColor: "rgba(255, 255, 255, 0.1)" },
                      "&:hover fieldset": { borderColor: "rgba(255, 255, 255, 0.2)" },
                      "&.Mui-focused fieldset": { borderColor: "#10b981" },
                    },
                  }}
                />
              </Box>

              <Button
                type="submit"
                variant="contained"
                fullWidth
                disabled={loading}
                sx={{
                  mt: 1,
                  py: 1.1,
                  borderRadius: 2,
                  bgcolor: "#10b981",
                  color: "#ffffff",
                  fontWeight: 700,
                  fontSize: "0.95rem",
                  textTransform: "none",
                  boxShadow: "0 4px 14px 0 rgba(16, 185, 129, 0.35)",
                  "&:hover": {
                    bgcolor: "#059669",
                    boxShadow: "0 6px 20px rgba(16, 185, 129, 0.45)",
                  },
                }}
              >
                {loading ? <CircularProgress size={22} color="inherit" /> : "Sign In"}
              </Button>
            </Stack>
          </Box>

          <Typography
            variant="caption"
            sx={{
              display: "block",
              textAlign: "center",
              color: "#64748b",
              mt: 3.5,
              fontSize: "0.75rem",
            }}
          >
            Pendaftaran publik dinonaktifkan untuk keamanan instance.
          </Typography>
        </CardContent>
      </Card>
    </Box>
  )
}
