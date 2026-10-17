// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useEffect } from "react"
import { Box, Button, Stack, CircularProgress } from "@mui/material"
import SendIcon from "@mui/icons-material/SendOutlined"
import LogoutIcon from "@mui/icons-material/LogoutOutlined"

/**
 * The body of one messaging app's tab in the Settings → Messaging dialog.
 *
 * Replaces the old /messaging page's per-app card (Messaging moved into
 * Settings). The card had to draw its own header and sit in a grid;
 * inside a tab none of that applies — the tab IS the header and only one
 * channel is visible at a time — so this is just the state machine:
 *
 *   unavailable → the install hint, nothing else
 *   connected   → connectedSlot + Send test message / Disconnect
 *   awaiting    → awaitingSlot + Refresh status / Cancel (auto-polls every 5s)
 *   otherwise   → defaultSlot (help copy, token fields or QR, Connect)
 *
 * Every connect / test / disconnect call still comes from useMessagingChannel,
 * unchanged — live connect flows can't be regression-tested without real
 * credentials, so the network side was deliberately not touched.
 */
/**
 * A contained button in an app's own brand colour.
 *
 * `bgcolor` alone is not enough: the theme's containedPrimary paints a
 * `background` GRADIENT (theme.js), which sits on top of background-color —
 * so every "brand" button on the old Messaging page actually rendered in the
 * app's orange, and a disabled one stayed orange. Clearing the image in every
 * state lets the brand colour (or the neutral disabled grey) show through.
 */
export function brandButtonSx(color, hover) {
  return {
    backgroundImage: "none", bgcolor: color, color: "#fff",
    "&:hover": { backgroundImage: "none", bgcolor: hover || color, animation: "none" },
    "&.Mui-disabled": { backgroundImage: "none", bgcolor: "action.disabledBackground", color: "action.disabled" },
  }
}

export default function ChannelPanel({
  brandColor,
  brandHoverColor,
  isConnected,
  isAwaiting,
  testing,
  onTest,
  onDisconnect,
  onRefresh,
  connectedSlot,
  awaitingSlot,
  defaultSlot,
  unavailableSlot,
}) {
  // Poll while waiting for the user to message their bot, so the tab flips to
  // Connected on its own. Runs only while this tab is mounted — i.e. while the
  // dialog is open on it — and stops the moment the state moves on.
  useEffect(() => {
    if (!isAwaiting || !onRefresh) return undefined
    const id = setInterval(() => { onRefresh() }, 5000)
    return () => clearInterval(id)
  }, [isAwaiting, onRefresh])

  const brandSx = brandColor ? brandButtonSx(brandColor, brandHoverColor) : undefined

  if (unavailableSlot) return <Box>{unavailableSlot}</Box>

  if (isConnected) {
    return (
      <Stack spacing={2}>
        {connectedSlot}
        <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
          <Button
            variant="contained" disableElevation
            startIcon={testing ? <CircularProgress size={16} color="inherit" /> : <SendIcon />}
            onClick={onTest}
            disabled={testing}
            sx={brandSx}
          >
            Send test message
          </Button>
          <Button variant="outlined" color="error" startIcon={<LogoutIcon />} onClick={onDisconnect}>
            Disconnect
          </Button>
        </Stack>
      </Stack>
    )
  }

  if (isAwaiting) {
    return (
      <Stack spacing={2}>
        {awaitingSlot}
        <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
          <Button variant="outlined" onClick={onRefresh}>Refresh status</Button>
          <Button variant="outlined" color="error" startIcon={<LogoutIcon />} onClick={onDisconnect}>
            Cancel
          </Button>
        </Stack>
      </Stack>
    )
  }

  return <Box>{defaultSlot}</Box>
}
