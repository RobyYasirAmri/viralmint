// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import {
  Box, Dialog, DialogContent, DialogTitle, IconButton, Stack, Tab, Tabs, Typography, alpha, useTheme,
} from "@mui/material"
import CloseIcon from "@mui/icons-material/CloseOutlined"
import { CHANNELS, ChannelBody, channelStatus } from "./channels"

/** The small status dot on a tab — colour carries state, the tab label says who. */
export function StatusDot({ tone, size = 8 }) {
  const theme = useTheme()
  const color = {
    connected: theme.palette.success.main,
    pending: theme.palette.warning.main,
    unavailable: theme.palette.text.disabled,
  }[tone]
  if (!color) return null
  return (
    <Box
      component="span"
      aria-hidden
      sx={{
        width: size, height: size, borderRadius: "50%", bgcolor: color, flexShrink: 0,
        boxShadow: tone === "connected" ? `0 0 0 3px ${alpha(color, 0.18)}` : "none",
      }}
    />
  )
}

/**
 * Setup for the four messaging apps, one tab each.
 *
 * Opened from a tile in Settings → Messaging, already on that app's tab. Only
 * the active tab's body is mounted, so an awaiting channel polls its status
 * while you are looking at it and not otherwise.
 *
 * Closing the dialog never cancels anything: a WhatsApp pairing in progress
 * keeps its QR (the hook holds it) and the tile says "Scan QR code" until you
 * come back or cancel it here.
 */
export default function MessagingDialog({ open, tab, onTab, onClose, channels, onRefresh }) {
  const theme = useTheme()
  const dark = theme.palette.mode === "dark"
  const meta = CHANNELS.find((c) => c.key === tab) || CHANNELS[0]

  return (
    <Dialog
      open={open} onClose={onClose} maxWidth="sm" fullWidth
      aria-labelledby="messaging-dialog-title"
      slotProps={{ paper: { "data-testid": "messaging-dialog", sx: { borderRadius: 3 } } }}
    >
      <DialogTitle id="messaging-dialog-title" sx={{ pr: 7, pb: 1 }}>
        <Typography component="span" variant="h6" sx={{ fontWeight: 700, display: "block" }}>
          Messaging apps
        </Typography>
        <Typography component="span" variant="body2" color="text.secondary" sx={{ display: "block" }}>
          Chat with ViralMint from your phone and hear when a job finishes.
        </Typography>
        <IconButton
          onClick={onClose} size="small" aria-label="Close"
          sx={{ position: "absolute", right: 12, top: 12 }}
        >
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>

      <Tabs
        value={meta.key}
        onChange={(_, v) => onTab(v)}
        variant="fullWidth"
        aria-label="Messaging apps"
        sx={{
          px: 2, borderBottom: 1, borderColor: "divider", minHeight: 52,
          "& .MuiTab-root": { textTransform: "none", fontWeight: 600, minHeight: 52, gap: 0.75 },
          // The readable per-theme colour, not the raw brand hex: Slack's
          // aubergine all but vanished as an underline on a dark surface.
          "& .MuiTabs-indicator": {
            height: 3, borderRadius: "3px 3px 0 0",
            bgcolor: dark ? meta.iconColor.dark : meta.iconColor.light,
          },
        }}
      >
        {CHANNELS.map((c) => {
          const s = channelStatus(c.key, channels[c.key])
          const selected = c.key === meta.key
          return (
            <Tab
              key={c.key}
              value={c.key}
              id={`messaging-tab-${c.key}`}
              aria-controls={`messaging-panel-${c.key}`}
              // The dot is decorative, so the state goes into the accessible name.
              aria-label={`${c.name}, ${s.label}`}
              iconPosition="start"
              icon={<c.Icon sx={{ fontSize: 20, color: dark ? c.iconColor.dark : c.iconColor.light }} />}
              label={
                <Stack direction="row" spacing={0.75} alignItems="center" component="span">
                  <Box component="span" sx={{ color: selected ? "text.primary" : "text.secondary" }}>
                    {c.name}
                  </Box>
                  <StatusDot tone={s.tone} />
                </Stack>
              }
            />
          )
        })}
      </Tabs>

      <DialogContent
        role="tabpanel"
        id={`messaging-panel-${meta.key}`}
        aria-labelledby={`messaging-tab-${meta.key}`}
        sx={{ pt: "20px !important", pb: 3, minHeight: 280 }}
      >
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {meta.caption}
        </Typography>
        <ChannelBody key={meta.key} meta={meta} ch={channels[meta.key]} onRefresh={onRefresh} />
      </DialogContent>
    </Dialog>
  )
}
