// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useState, useEffect, useCallback, useMemo, useRef } from "react"
import http from "../api/http"
import { ws } from "../api/websocket"
import useAppStore from "../store/appStore"

/**
 * useMessagingChannel — shared connect/disconnect/test lifecycle for the
 * four messaging channels (Telegram / WhatsApp / Discord / Slack), used by
 * Settings → Messaging (components/settings/MessagingSection.jsx).
 *
 * Each channel differs only by endpoint path, token fields, status-branch
 * shape, and user-facing copy — all captured in the CHANNELS descriptor map
 * below. The endpoint paths, request payload field names, WS event handling
 * and snackbar copy are a mechanical lift from the retired pages/Messaging.jsx
 * and MUST stay byte-identical (live connect flows can't be regression-tested
 * without real creds).
 *
 * Usage:
 *   const tg = useMessagingChannel("telegram")
 *   tg.state       — channel state string (compare against the exported enums)
 *   tg.info        — channel info object (bot_username / chat_id / …)
 *   tg.qr          — WhatsApp pair QR string (empty for other channels)
 *   tg.saving      — connect in flight
 *   tg.testing     — test message in flight
 *   tg.tokens      — token-field values keyed by payload field name
 *   tg.setToken(field, value)
 *   tg.connect() / tg.disconnect() / tg.test()
 *   tg.chip        — { label, color?, connected? } (label for the status chip)
 *   tg.applyStatus(slice) — apply this channel's slice of GET /api/messaging/status
 */

export const STATE = {
  DISCONNECTED: "disconnected",
  CONNECTING: "connecting",
  AWAITING_START: "awaiting_start",
  CONNECTED: "connected",
  // Paired, but the link is down for now and the backend is bringing it back
  // on its own. Shown like Connected (Test / Disconnect) — never the connect
  // or pairing screens, whose buttons would throw a working pairing away.
  RECONNECTING: "reconnecting",
}

export const WA_STATE = {
  DISCONNECTED: "disconnected",
  PAIRING: "pairing",
  CONNECTED: "connected",
  RECONNECTING: "reconnecting",
  UNAVAILABLE: "unavailable",
}

export const DC_STATE = {
  DISCONNECTED: "disconnected",
  CONNECTING: "connecting",
  AWAITING_DM: "awaiting_dm",
  CONNECTED: "connected",
  RECONNECTING: "reconnecting",
  UNAVAILABLE: "unavailable",
}

export const SL_STATE = {
  DISCONNECTED: "disconnected",
  CONNECTING: "connecting",
  AWAITING_DM: "awaiting_dm",
  CONNECTED: "connected",
  UNAVAILABLE: "unavailable",
}

const CHANNELS = {
  telegram: {
    states: STATE,
    emptyInfo: { bot_username: "", bot_url: "", chat_id: "", pair_code: "" },
    tokenFields: ["bot_token"],
    applyStatus: (tg, { setState, setInfo }) => {
      if (tg.connected && tg.chat_id) {
        setState(STATE.CONNECTED)
        setInfo({ bot_username: tg.bot_username || "", bot_url: tg.bot_url || "", chat_id: tg.chat_id || "", pair_code: "" })
      } else if (tg.retrying) {
        // The saved bot failed to start (offline at boot); a retry is scheduled.
        setState(STATE.RECONNECTING)
        setInfo({ bot_username: "", bot_url: "", chat_id: "", pair_code: "" })
      } else if (tg.bot_username) {
        // bot_url carries ?start=<pair_code> while unpaired — one tap pairs.
        setState(STATE.AWAITING_START)
        setInfo({ bot_username: tg.bot_username || "", bot_url: tg.bot_url || "", chat_id: "", pair_code: tg.pair_code || "" })
      } else {
        setState(STATE.DISCONNECTED)
        setInfo({ bot_username: "", bot_url: "", chat_id: "", pair_code: "" })
      }
    },
    connect: {
      validate: (t) => (!t.bot_token.trim() ? "Paste your bot token first" : null),
      pendingState: STATE.CONNECTING,
      payload: (t) => ({ bot_token: t.bot_token.trim() }),
      mapInfo: (data) => ({
        bot_username: data.bot_username || "",
        bot_url: data.bot_url || (data.bot_username ? `https://t.me/${data.bot_username}` : ""),
        chat_id: data.chat_id || "",
        pair_code: data.pair_code || "",
      }),
      awaitingState: STATE.AWAITING_START,
      connectedMessage: "Telegram connected",
      awaitingMessage: "Bot ready — open it and tap Start to link your account",
      failMessage: "Connect failed",
    },
    disconnectMessage: "Telegram disconnected",
    test: { success: "Test message sent — check Telegram", fail: "Test failed — link the bot to your account first" },
    chip: (state) => {
      if (state === STATE.CONNECTED) return { label: "Connected", connected: true }
      if (state === STATE.AWAITING_START) return { label: "Needs pairing", color: "warning" }
      if (state === STATE.RECONNECTING) return { label: "Reconnecting…", color: "warning" }
      if (state === STATE.CONNECTING) return { label: "Connecting…" }
      return { label: "Not connected" }
    },
    events: {
      telegram_connected: (msg, { setState, setInfo, showSnackbar }) => {
        setState(STATE.CONNECTED)
        setInfo(prev => ({ ...prev, chat_id: msg.chat_id || prev.chat_id }))
        showSnackbar("Telegram connected — you'll receive notifications here", "success")
      },
    },
  },

  whatsapp: {
    states: WA_STATE,
    emptyInfo: { chat_id: "", error: "" },
    tokenFields: [],
    clearQrOnDisconnect: true,
    applyStatus: (wa, { setState, setInfo, setQr }) => {
      if (wa.installed === false) {
        setState(WA_STATE.UNAVAILABLE)
        setInfo({ chat_id: "", error: wa.error || "neonize not installed" })
      } else if (wa.connected) {
        setState(WA_STATE.CONNECTED)
        setInfo({ chat_id: wa.chat_id || "", error: "" })
        setQr("")
      } else if (wa.paired) {
        setState(WA_STATE.RECONNECTING)
        setInfo({ chat_id: wa.chat_id || "", error: "" })
        setQr("")
      } else if (wa.pairing) {
        setState(WA_STATE.PAIRING)
      } else {
        setState(WA_STATE.DISCONNECTED)
        setInfo({ chat_id: "", error: "" })
        setQr("")
      }
    },
    connect: {
      // WhatsApp pairs via QR — no token payload, no CONNECTING state.
      custom: async ({ setSaving, setState, setQr, showSnackbar }) => {
        setSaving(true)
        setQr("")
        try {
          await http.post("/api/messaging/whatsapp/connect")
          setState(WA_STATE.PAIRING)
          showSnackbar("Generating QR code — scan it from your phone", "info")
        } catch (e) {
          setState(WA_STATE.DISCONNECTED)
          showSnackbar(e.response?.data?.detail || "WhatsApp connect failed", "error")
        } finally {
          setSaving(false)
        }
      },
    },
    disconnectMessage: "WhatsApp disconnected",
    test: { success: "Test message sent — check WhatsApp", fail: "Test failed — is WhatsApp paired?" },
    chip: (state) => {
      if (state === WA_STATE.CONNECTED) return { label: "Connected", connected: true }
      if (state === WA_STATE.PAIRING) return { label: "Scan QR code", color: "warning" }
      if (state === WA_STATE.RECONNECTING) return { label: "Reconnecting…", color: "warning" }
      if (state === WA_STATE.UNAVAILABLE) return { label: "Unavailable" }
      return { label: "Not connected" }
    },
    events: {
      whatsapp_qr: (msg, { setState, setQr }) => {
        setQr(msg.qr || "")
        setState(WA_STATE.PAIRING)
      },
      whatsapp_connected: (msg, { setState, setInfo, setQr }) => {
        setState(WA_STATE.CONNECTED)
        setInfo({ chat_id: msg.chat_id || "", error: "" })
        setQr("")
      },
      whatsapp_disconnected: (msg, { setState, setInfo, setQr }) => {
        // "disconnected" is a transient network drop — neonize reconnects by
        // itself and the session stays paired. Only a log-out or an explicit
        // disconnect (no reason) ends the pairing.
        if (msg.reason === "disconnected") {
          setState(s => (s === WA_STATE.CONNECTED ? WA_STATE.RECONNECTING : s))
          return
        }
        setState(WA_STATE.DISCONNECTED)
        setInfo({ chat_id: "", error: "" })
        setQr("")
      },
    },
  },

  discord: {
    states: DC_STATE,
    emptyInfo: { bot_username: "", bot_invite_url: "", chat_id: "", error: "", pair_code: "" },
    tokenFields: ["bot_token"],
    applyStatus: (dc, { setState, setInfo }) => {
      if (dc.installed === false) {
        setState(DC_STATE.UNAVAILABLE)
        setInfo({ bot_username: "", bot_invite_url: "", chat_id: "", error: dc.error || "discord.py not installed" })
      } else if (dc.connected) {
        setState(DC_STATE.CONNECTED)
        setInfo({
          bot_username: dc.bot_username || "",
          bot_invite_url: dc.bot_invite_url || "",
          chat_id: dc.chat_id || "",
          error: "",
        })
      } else if (dc.chat_id) {
        // Paired, but the gateway isn't ready (a drop, or still logging in).
        setState(DC_STATE.RECONNECTING)
        setInfo({
          bot_username: dc.bot_username || "",
          bot_invite_url: dc.bot_invite_url || "",
          chat_id: dc.chat_id || "",
          error: "",
        })
      } else if (dc.bot_username) {
        setState(DC_STATE.AWAITING_DM)
        setInfo({
          bot_username: dc.bot_username || "",
          bot_invite_url: dc.bot_invite_url || "",
          chat_id: "",
          error: "",
          pair_code: dc.pair_code || "",
        })
      } else {
        setState(DC_STATE.DISCONNECTED)
        setInfo({ bot_username: "", bot_invite_url: "", chat_id: "", error: "" })
      }
    },
    connect: {
      validate: (t) => (!t.bot_token.trim() ? "Paste your Discord bot token first" : null),
      pendingState: DC_STATE.CONNECTING,
      payload: (t) => ({ bot_token: t.bot_token.trim() }),
      mapInfo: (data) => ({
        bot_username: data.bot_username || "",
        bot_invite_url: data.bot_invite_url || "",
        chat_id: data.chat_id || "",
        error: "",
        pair_code: data.pair_code || "",
      }),
      awaitingState: DC_STATE.AWAITING_DM,
      connectedMessage: "Discord connected",
      awaitingMessage: "Bot online — DM it the pairing code to finish setup",
      failMessage: "Discord connect failed",
    },
    disconnectMessage: "Discord disconnected",
    test: { success: "Test message sent — check Discord", fail: "Test failed — DM your bot the pairing code first" },
    chip: (state) => {
      if (state === DC_STATE.CONNECTED) return { label: "Connected", connected: true }
      if (state === DC_STATE.AWAITING_DM) return { label: "Needs pairing", color: "warning" }
      if (state === DC_STATE.RECONNECTING) return { label: "Reconnecting…", color: "warning" }
      if (state === DC_STATE.CONNECTING) return { label: "Connecting…" }
      if (state === DC_STATE.UNAVAILABLE) return { label: "Unavailable" }
      return { label: "Not connected" }
    },
    events: {
      discord_connected: (msg, { setState, setInfo, showSnackbar }) => {
        setState(DC_STATE.CONNECTED)
        setInfo(prev => ({ ...prev, chat_id: msg.chat_id || prev.chat_id }))
        showSnackbar("Discord connected — you'll receive notifications here", "success")
      },
    },
  },

  slack: {
    states: SL_STATE,
    emptyInfo: { bot_user_id: "", team_name: "", chat_id: "", error: "", pair_code: "" },
    tokenFields: ["bot_token", "app_token"],
    applyStatus: (sl, { setState, setInfo }) => {
      if (sl.installed === false) {
        setState(SL_STATE.UNAVAILABLE)
        setInfo({ bot_user_id: "", team_name: "", chat_id: "", error: sl.error || "slack-sdk not installed" })
      } else if (sl.connected) {
        setState(SL_STATE.CONNECTED)
        setInfo({
          bot_user_id: sl.bot_user_id || "",
          team_name: sl.team_name || "",
          chat_id: sl.chat_id || "",
          error: "",
        })
      } else if (sl.awaiting_dm) {
        setState(SL_STATE.AWAITING_DM)
        setInfo({
          bot_user_id: sl.bot_user_id || "",
          team_name: sl.team_name || "",
          chat_id: "",
          error: "",
          pair_code: sl.pair_code || "",
        })
      } else {
        setState(SL_STATE.DISCONNECTED)
        setInfo({ bot_user_id: "", team_name: "", chat_id: "", error: "" })
      }
    },
    connect: {
      validate: (t) => (
        (!t.bot_token.trim() || !t.app_token.trim())
          ? "Paste both the bot token (xoxb-) and app-level token (xapp-)"
          : null
      ),
      pendingState: SL_STATE.CONNECTING,
      payload: (t) => ({
        bot_token: t.bot_token.trim(),
        app_token: t.app_token.trim(),
      }),
      mapInfo: (data) => ({
        bot_user_id: data.bot_user_id || "",
        team_name: data.team_name || "",
        chat_id: data.chat_id || "",
        error: "",
        pair_code: data.pair_code || "",
      }),
      awaitingState: SL_STATE.AWAITING_DM,
      connectedMessage: "Slack connected",
      awaitingMessage: "Bot online — DM it the pairing code to finish setup",
      failMessage: "Slack connect failed",
    },
    disconnectMessage: "Slack disconnected",
    test: { success: "Test message sent — check Slack", fail: "Test failed — DM your bot the pairing code first" },
    chip: (state) => {
      if (state === SL_STATE.CONNECTED) return { label: "Connected", connected: true }
      if (state === SL_STATE.AWAITING_DM) return { label: "Needs pairing", color: "warning" }
      if (state === SL_STATE.CONNECTING) return { label: "Connecting…" }
      if (state === SL_STATE.UNAVAILABLE) return { label: "Unavailable" }
      return { label: "Not connected" }
    },
    events: {
      slack_connected: (msg, { setState, setInfo, showSnackbar }) => {
        setState(SL_STATE.CONNECTED)
        setInfo(prev => ({ ...prev, chat_id: msg.chat_id || prev.chat_id }))
        showSnackbar("Slack connected — you'll receive notifications here", "success")
      },
    },
  },
}

export default function useMessagingChannel(channelKey) {
  const cfg = CHANNELS[channelKey]
  const showSnackbar = useAppStore((s) => s.showSnackbar)

  const [state, setState] = useState(cfg.states.DISCONNECTED)
  const [info, setInfo] = useState(cfg.emptyInfo)
  const [qr, setQr] = useState("")
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)

  const emptyTokens = useMemo(
    () => Object.fromEntries((cfg.tokenFields || []).map((f) => [f, ""])),
    [cfg],
  )
  const [tokens, setTokens] = useState(emptyTokens)
  const tokensRef = useRef(tokens)
  tokensRef.current = tokens

  // Stable helper bundle passed to descriptor callbacks (state setters are
  // stable by React contract; showSnackbar is a stable zustand selector).
  const helpers = useMemo(
    () => ({ setState, setInfo, setQr, setSaving, showSnackbar }),
    [showSnackbar],
  )

  const setToken = useCallback((field, value) => {
    setTokens((prev) => ({ ...prev, [field]: value }))
  }, [])

  const applyStatus = useCallback((statusSlice) => {
    cfg.applyStatus(statusSlice, helpers)
  }, [cfg, helpers])

  const connect = useCallback(async () => {
    if (cfg.connect.custom) {
      await cfg.connect.custom(helpers)
      return
    }
    const warning = cfg.connect.validate?.(tokensRef.current)
    if (warning) {
      showSnackbar(warning, "warning")
      return
    }
    setSaving(true)
    setState(cfg.connect.pendingState)
    try {
      const { data } = await http.post(
        `/api/messaging/${channelKey}/connect`,
        cfg.connect.payload(tokensRef.current),
      )
      setInfo(cfg.connect.mapInfo(data))
      setState(data.chat_id ? cfg.states.CONNECTED : cfg.connect.awaitingState)
      setTokens(emptyTokens)
      showSnackbar(
        data.chat_id ? cfg.connect.connectedMessage : cfg.connect.awaitingMessage,
        "success",
      )
    } catch (e) {
      setState(cfg.states.DISCONNECTED)
      showSnackbar(e.response?.data?.detail || cfg.connect.failMessage, "error")
    } finally {
      setSaving(false)
    }
  }, [cfg, channelKey, helpers, emptyTokens, showSnackbar])

  const disconnect = useCallback(async () => {
    try {
      await http.post(`/api/messaging/${channelKey}/disconnect`)
      setState(cfg.states.DISCONNECTED)
      setInfo(cfg.emptyInfo)
      if (cfg.clearQrOnDisconnect) setQr("")
      showSnackbar(cfg.disconnectMessage, "info")
    } catch (e) {
      showSnackbar(e.response?.data?.detail || "Disconnect failed", "error")
    }
  }, [cfg, channelKey, showSnackbar])

  const test = useCallback(async () => {
    setTesting(true)
    try {
      await http.post(`/api/messaging/${channelKey}/test`)
      showSnackbar(cfg.test.success, "success")
    } catch (e) {
      showSnackbar(e.response?.data?.detail || cfg.test.fail, "error")
    } finally {
      setTesting(false)
    }
  }, [cfg, channelKey, showSnackbar])

  // Per-channel WS subscriptions (telegram/discord/slack `*_connected`,
  // WhatsApp QR pairing events).
  useEffect(() => {
    const unsubs = Object.entries(cfg.events || {}).map(
      ([evt, handler]) => ws.on(evt, (msg) => handler(msg, helpers)),
    )
    return () => { unsubs.forEach(fn => fn()) }
  }, [cfg, helpers])

  const chip = cfg.chip(state)

  return {
    state, info, qr, saving, testing,
    tokens, setToken,
    connect, disconnect, test,
    chip, applyStatus,
  }
}

// Exported for unit tests of the status → state mapping only.
export { CHANNELS as CHANNEL_CONFIG }
