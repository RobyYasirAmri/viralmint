// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useCallback, useEffect, useRef, useState } from "react"
import { useLocation, useNavigate, useSearchParams } from "react-router-dom"
import {
  Box, ButtonBase, Grid, Skeleton, Stack, Typography, alpha, useTheme,
} from "@mui/material"
import ChevronRightIcon from "@mui/icons-material/ChevronRight"
import http from "../../api/http"
import useAppStore from "../../store/appStore"
import useMessagingChannel from "../../hooks/useMessagingChannel"
import useHashHighlight from "../../hooks/useHashHighlight"
import MessagingDialog, { StatusDot } from "../messaging/MessagingDialog"
import { CHANNELS, channelStatus } from "../messaging/channels"

/**
 * Settings → Messaging: the four messaging apps at a glance, set up in a
 * tabbed dialog.
 *
 * This used to be its own page at /messaging. Connecting a phone is a
 * one-time setup step, so it belongs with the other setup, and the page's
 * four always-open cards were mostly instructions for apps you are never
 * going to use. Now each app is one tile saying whether it is connected;
 * clicking opens the dialog on that app's tab. /messaging redirects to
 * /settings#messaging, and this section scrolls itself into view on that hash.
 *
 * `?messaging=<telegram|whatsapp|discord|slack>` opens the dialog on that tab
 * (the one-time "connect Telegram" nudge links here). The parameter is
 * removed once used, so a reload or Back does not reopen it.
 *
 * The four channel hooks live HERE rather than in the dialog, so the tiles and
 * the tabs read one state and the WebSocket `*_connected` / WhatsApp QR events
 * keep landing while the dialog is closed.
 */
export default function MessagingSection() {
  const theme = useTheme()
  const dark = theme.palette.mode === "dark"
  const showSnackbar = useAppStore((s) => s.showSnackbar)
  const anchorRef = useRef(null)
  const highlight = useHashHighlight("messaging", anchorRef)
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const location = useLocation()

  const telegram = useMessagingChannel("telegram")
  const whatsapp = useMessagingChannel("whatsapp")
  const discord = useMessagingChannel("discord")
  const slack = useMessagingChannel("slack")
  const channels = { telegram, whatsapp, discord, slack }

  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState(CHANNELS[0].key)

  const fetchStatus = useCallback(async () => {
    try {
      const { data } = await http.get("/api/messaging/status")
      telegram.applyStatus(data.telegram || {})
      whatsapp.applyStatus(data.whatsapp || {})
      discord.applyStatus(data.discord || {})
      slack.applyStatus(data.slack || {})
    } catch {
      showSnackbar("Couldn't load messaging status", "error")
    } finally {
      setLoading(false)
    }
  }, [telegram.applyStatus, whatsapp.applyStatus, discord.applyStatus, slack.applyStatus, showSnackbar])

  useEffect(() => { fetchStatus() }, [fetchStatus])

  // Deep link: open straight onto one app's tab.
  const requested = searchParams.get("messaging")
  useEffect(() => {
    if (!requested) return
    if (CHANNELS.some((c) => c.key === requested)) {
      setTab(requested)
      setOpen(true)
    }
    const next = new URLSearchParams(searchParams)
    next.delete("messaging")
    // setSearchParams would drop the #messaging hash (react-router resolves
    // only the new search), which would cancel the scroll-to-section and the
    // arrival pulse. Keep the hash.
    const search = next.toString()
    navigate({ search: search ? `?${search}` : "", hash: location.hash }, { replace: true })
  }, [requested]) // eslint-disable-line react-hooks/exhaustive-deps

  const openOn = (key) => { setTab(key); setOpen(true) }
  const close = () => { setOpen(false); fetchStatus() }

  const statuses = CHANNELS.map((c) => ({ meta: c, s: channelStatus(c.key, channels[c.key]) }))
  const connectedCount = statuses.filter((x) => x.s.tone === "connected").length

  return (
    <Box id="messaging" ref={anchorRef} sx={{ scrollMarginTop: 16 }}>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {connectedCount === 0
          ? "Connect a messaging app to chat with ViralMint from your phone and get a message when a scout, download or video finishes."
          : `${connectedCount} of ${CHANNELS.length} connected. Job notifications go to every connected app, and you can chat with ViralMint from any of them.`}
      </Typography>

      <Grid
        container spacing={1.5}
        sx={{
          borderRadius: 2,
          transition: "box-shadow 400ms",
          boxShadow: highlight ? `0 0 0 3px ${alpha(theme.palette.primary.main, 0.35)}` : "none",
        }}
      >
        {statuses.map(({ meta, s }) => {
          const iconColor = dark ? meta.iconColor.dark : meta.iconColor.light
          return (
            <Grid key={meta.key} size={{ xs: 12, sm: 6 }}>
              {loading ? (
                <Skeleton variant="rounded" height={68} />
              ) : (
                <ButtonBase
                  onClick={() => openOn(meta.key)}
                  aria-label={`${meta.name}: ${s.label}. ${s.tone === "connected" ? "Manage" : "Set up"}`}
                  data-testid={`messaging-tile-${meta.key}`}
                  sx={{
                    width: "100%", textAlign: "left", borderRadius: 2, p: 1.5,
                    border: 1,
                    borderColor: s.tone === "connected" ? alpha(theme.palette.success.main, 0.45) : "divider",
                    bgcolor: s.tone === "connected" ? alpha(theme.palette.success.main, 0.05) : "transparent",
                    transition: "border-color 140ms, background-color 140ms",
                    "&:hover": { borderColor: alpha(iconColor, 0.6), bgcolor: "action.hover" },
                    "&:focus-visible": { outline: `2px solid ${theme.palette.primary.main}`, outlineOffset: 2 },
                  }}
                >
                  <Stack direction="row" spacing={1.5} alignItems="center" sx={{ width: "100%", minWidth: 0 }}>
                    <Box sx={{
                      width: 40, height: 40, borderRadius: 2, flexShrink: 0,
                      display: "grid", placeItems: "center",
                      bgcolor: alpha(iconColor, 0.14), color: iconColor,
                      boxShadow: `inset 0 0 0 1px ${alpha(iconColor, 0.25)}`,
                    }}>
                      <meta.Icon sx={{ fontSize: 22 }} />
                    </Box>
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Stack direction="row" spacing={0.75} alignItems="center">
                        <Typography sx={{ fontWeight: 700, fontSize: "0.92rem" }}>{meta.name}</Typography>
                        <StatusDot tone={s.tone} />
                      </Stack>
                      <Typography
                        variant="caption" noWrap title={s.detail}
                        sx={{
                          display: "block",
                          color: s.tone === "pending" ? "warning.main" : "text.secondary",
                          fontWeight: s.tone === "pending" ? 600 : 400,
                        }}
                      >
                        {s.detail}
                      </Typography>
                    </Box>
                    <Typography
                      component="span" variant="caption"
                      sx={{ color: "text.secondary", fontWeight: 600, flexShrink: 0 }}
                    >
                      {s.tone === "connected" ? "Manage" : s.tone === "pending" ? "Finish" : "Set up"}
                    </Typography>
                    <ChevronRightIcon sx={{ color: "text.secondary", fontSize: 20, flexShrink: 0, ml: "-4px !important" }} />
                  </Stack>
                </ButtonBase>
              )}
            </Grid>
          )
        })}
      </Grid>

      <MessagingDialog
        open={open}
        tab={tab}
        onTab={setTab}
        onClose={close}
        channels={channels}
        onRefresh={fetchStatus}
      />
    </Box>
  )
}
