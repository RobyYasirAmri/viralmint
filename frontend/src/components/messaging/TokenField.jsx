// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useState } from "react"
import { TextField, IconButton, InputAdornment } from "@mui/material"
import VisibilityIcon from "@mui/icons-material/VisibilityOutlined"
import VisibilityOffIcon from "@mui/icons-material/VisibilityOffOutlined"

/**
 * Password-style token input with a show/hide reveal toggle, so users can
 * verify a pasted bot token before connecting. Defaults match the Messaging
 * setup dialog's token fields (fullWidth / small / autoComplete off).
 */
export default function TokenField({ label, placeholder, value, onChange, disabled }) {
  const [show, setShow] = useState(false)
  return (
    <TextField
      label={label}
      type={show ? "text" : "password"}
      fullWidth
      size="small"
      placeholder={placeholder}
      value={value}
      onChange={onChange}
      disabled={disabled}
      autoComplete="off"
      InputProps={{
        endAdornment: (
          <InputAdornment position="end">
            <IconButton
              aria-label={show ? "Hide token" : "Show token"}
              onClick={() => setShow((s) => !s)}
              edge="end"
              size="small"
            >
              {show ? <VisibilityOffIcon fontSize="small" /> : <VisibilityIcon fontSize="small" />}
            </IconButton>
          </InputAdornment>
        ),
      }}
    />
  )
}
