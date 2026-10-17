// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useState } from "react"
import {
  Box, Typography, Button, Stack, CircularProgress, Alert, Link, IconButton, Tooltip,
} from "@mui/material"
import ContentCopyIcon from "@mui/icons-material/ContentCopyOutlined"
import CheckIcon from "@mui/icons-material/Check"
import TelegramIcon from "@mui/icons-material/Telegram"
import WhatsAppIcon from "@mui/icons-material/WhatsApp"
import QrCodeIcon from "@mui/icons-material/QrCode2Outlined"
import ChatBubbleIcon from "@mui/icons-material/ChatBubbleOutlined"
import TagIcon from "@mui/icons-material/TagOutlined"
import LogoutIcon from "@mui/icons-material/LogoutOutlined"
import { QRCodeCanvas } from "qrcode.react"
import { STATE, WA_STATE, DC_STATE, SL_STATE } from "../../hooks/useMessagingChannel"
import ChannelPanel, { brandButtonSx } from "./ChannelPanel"
import TokenField from "./TokenField"

/**
 * The four messaging apps: identity (name, glyph, brand colour) and the body
 * of each one's setup tab. The copy and the connect inputs are carried over
 * from the old /messaging page (now Settings → Messaging); only the framing
 * changed.
 *
 * `iconColor` is a pair because Slack's aubergine is unreadable on a dark
 * surface; the other three brand colours hold up in both themes.
 */
export const CHANNELS = [
  {
    key: "telegram", name: "Telegram", Icon: TelegramIcon,
    brand: "#229ED9", brandHover: "#1B87BA",
    iconColor: { light: "#229ED9", dark: "#4FB4E6" },
    caption: "Two-way chat with ViralMint plus job notifications, through a bot you create.",
  },
  {
    key: "whatsapp", name: "WhatsApp", Icon: WhatsAppIcon,
    brand: "#25D366", brandHover: "#128C7E",
    iconColor: { light: "#1DAA52", dark: "#25D366" },
    caption: "Two-way chat plus notifications. Pairs by scanning a QR code, like WhatsApp Web.",
  },
  {
    key: "discord", name: "Discord", Icon: ChatBubbleIcon,
    brand: "#5865F2", brandHover: "#4752C4",
    iconColor: { light: "#5865F2", dark: "#7C87F5" },
    caption: "DM your bot to chat with ViralMint and get job notifications.",
  },
  {
    key: "slack", name: "Slack", Icon: TagIcon,
    brand: "#611F69", brandHover: "#4A154B",
    iconColor: { light: "#611F69", dark: "#D48FDD" },
    caption: "Socket Mode, so no public URL is needed. DM your bot to chat and get notifications.",
  },
]

const STATES = { telegram: STATE, whatsapp: WA_STATE, discord: DC_STATE, slack: SL_STATE }

/**
 * One status vocabulary for the tiles and the tab dots.
 *   tone: "connected" | "pending" (needs one more step) | "unavailable" | "off"
 *   detail: the short line under the app's name on its tile
 */
export function channelStatus(key, ch) {
  const S = STATES[key]
  if (ch.state === S.UNAVAILABLE) {
    return { tone: "unavailable", label: "Unavailable", detail: "Needs a missing package — open for details" }
  }
  if (ch.state === S.CONNECTED) {
    const who = {
      telegram: ch.info.bot_username && `@${ch.info.bot_username}`,
      whatsapp: "Paired with your phone",
      discord: ch.info.bot_username,
      slack: ch.info.team_name,
    }[key]
    return { tone: "connected", label: "Connected", detail: who || "Connected" }
  }
  if (ch.state === S.RECONNECTING) {
    return { tone: "pending", label: "Reconnecting…", detail: "Paired — reconnecting on its own" }
  }
  if (ch.state === S.AWAITING_START || ch.state === S.AWAITING_DM || ch.state === WA_STATE.PAIRING) {
    return { tone: "pending", label: ch.chip.label, detail: {
      telegram: "Link the bot to your account to finish",
      whatsapp: "Scan the QR code on your phone to finish",
      discord: "DM your bot the pairing code to finish",
      slack: "DM your bot the pairing code to finish",
    }[key] }
  }
  if (ch.state === S.CONNECTING) {
    return { tone: "pending", label: "Connecting…", detail: "Connecting…" }
  }
  return { tone: "off", label: "Not connected", detail: "Not connected" }
}

export function isAwaiting(key, ch) {
  const S = STATES[key]
  return ch.state === S.AWAITING_START || ch.state === S.AWAITING_DM
}

// Paired but offline for now: same actions as Connected, honest wording.
function ReconnectingNote() {
  return (
    <Alert severity="warning" variant="outlined">
      Paired, but the connection dropped. ViralMint is reconnecting on its own — there is
      nothing to redo. Messages sent meanwhile may arrive late.
    </Alert>
  )
}

function MissingPackage({ pkg, error }) {
  return (
    <Alert severity="warning" variant="outlined">
      This needs the <code>{pkg}</code> Python package. Install dependencies with{" "}
      <code>pip install -r requirements.txt</code>, then restart the app.
      {error && (
        <Typography variant="caption" display="block" sx={{ mt: 1, opacity: 0.8 }}>
          Details: {error}
        </Typography>
      )}
    </Alert>
  )
}

/**
 * The one-time pairing code, big enough to read off the screen, with a copy
 * button. The bot binds to whoever sends it and ignores everyone else, so the
 * copy says so — it is the reason the step exists.
 */
function PairCode({ code }) {
  const [copied, setCopied] = useState(false)
  if (!code) return null
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* clipboard blocked — the code is on screen */ }
  }
  return (
    <Stack direction="row" spacing={1} alignItems="center" data-testid="pair-code">
      <Box sx={{
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        fontSize: "1.35rem", fontWeight: 700, letterSpacing: "0.22em",
        px: 1.5, py: 0.5, borderRadius: 1.5,
        border: 1, borderColor: "divider", bgcolor: "action.hover",
      }}>
        {code}
      </Box>
      <Tooltip title={copied ? "Copied" : "Copy code"}>
        <IconButton size="small" onClick={copy} aria-label="Copy pairing code">
          {copied ? <CheckIcon fontSize="small" /> : <ContentCopyIcon fontSize="small" />}
        </IconButton>
      </Tooltip>
    </Stack>
  )
}

const PRIVATE_NOTE = "The bot links to whoever sends this code and ignores everyone else."

function BotLink({ url, name, fallback }) {
  if (url) {
    return <Link href={url} target="_blank" rel="noreferrer" sx={{ fontWeight: 600 }}>{name}</Link>
  }
  return <strong>{name || fallback}</strong>
}

function ConnectButton({ meta, onClick, disabled, busy, children, startIcon }) {
  return (
    <Box>
      <Button
        variant="contained" disableElevation
        onClick={onClick}
        disabled={disabled}
        startIcon={busy ? <CircularProgress size={16} color="inherit" /> : startIcon}
        sx={brandButtonSx(meta.brand, meta.brandHover)}
      >
        {children}
      </Button>
    </Box>
  )
}

function TelegramBody({ meta, ch, onRefresh }) {
  const bot = ch.info.bot_username ? `@${ch.info.bot_username}` : ""
  return (
    <ChannelPanel
      brandColor={meta.brand} brandHoverColor={meta.brandHover}
      isConnected={ch.state === STATE.CONNECTED || ch.state === STATE.RECONNECTING}
      isAwaiting={ch.state === STATE.AWAITING_START}
      testing={ch.testing} onTest={ch.test} onDisconnect={ch.disconnect} onRefresh={onRefresh}
      connectedSlot={ch.state === STATE.RECONNECTING ? <ReconnectingNote /> :
        <Alert severity="success" variant="outlined">
          Connected to <BotLink url={ch.info.bot_url} name={bot} />. Send any message to your
          bot to chat with ViralMint.
        </Alert>
      }
      awaitingSlot={
        <Alert severity="info" variant="outlined" icon={false}>
          <Stack spacing={1.25}>
            <Typography variant="body2">
              Bot ready. Open <BotLink url={ch.info.bot_url} name={bot} fallback="your bot" /> in
              Telegram and tap <strong>Start</strong> — the link carries your pairing code, so
              that one tap links the bot to your account. If Telegram doesn't show a Start
              button, send the bot this code:
            </Typography>
            <PairCode code={ch.info.pair_code} />
            <Typography variant="caption" color="text.secondary">{PRIVATE_NOTE}</Typography>
          </Stack>
        </Alert>
      }
      defaultSlot={
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            Create a bot with{" "}
            <Link href="https://t.me/BotFather" target="_blank" rel="noreferrer">@BotFather</Link>
            {" "}on Telegram (send <code>/newbot</code>), then paste the bot token below.
          </Typography>
          <TokenField
            label="Bot token"
            placeholder="123456789:ABCdef..."
            value={ch.tokens.bot_token}
            onChange={(e) => ch.setToken("bot_token", e.target.value)}
            disabled={ch.saving}
          />
          <ConnectButton
            meta={meta} onClick={ch.connect} busy={ch.saving}
            disabled={ch.saving || !ch.tokens.bot_token.trim()}
          >
            {ch.saving ? "Connecting…" : "Connect Telegram"}
          </ConnectButton>
        </Stack>
      }
    />
  )
}

function WhatsAppBody({ meta, ch, onRefresh }) {
  const pairing = ch.state === WA_STATE.PAIRING
  return (
    <ChannelPanel
      brandColor={meta.brand} brandHoverColor={meta.brandHover}
      isConnected={ch.state === WA_STATE.CONNECTED || ch.state === WA_STATE.RECONNECTING}
      isAwaiting={false}
      testing={ch.testing} onTest={ch.test} onDisconnect={ch.disconnect} onRefresh={onRefresh}
      unavailableSlot={ch.state === WA_STATE.UNAVAILABLE
        ? <MissingPackage pkg="neonize" error={ch.info.error} /> : null}
      connectedSlot={ch.state === WA_STATE.RECONNECTING ? <ReconnectingNote /> :
        <Alert severity="success" variant="outlined">
          WhatsApp is paired. To chat with ViralMint, write in your own <strong>Message
          yourself</strong> chat; job notifications arrive there too. Messages in any other chat
          are never read.
        </Alert>
      }
      defaultSlot={pairing ? (
        // The QR used to open in a second dialog stacked on the page. Inside
        // this tab it simply takes the tab's place until pairing completes.
        <Stack spacing={2} alignItems="center" data-testid="whatsapp-qr">
          <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center" }}>
            On your phone, open <strong>WhatsApp → Settings → Linked Devices → Link a Device</strong>,
            then scan this code.
          </Typography>
          {ch.qr ? (
            // White on purpose: a QR code needs a light background in either theme.
            <Box sx={{ p: 2, bgcolor: "#fff", borderRadius: 2, boxShadow: 1 }}>
              <QRCodeCanvas value={ch.qr} size={220} level="M" includeMargin={false} />
            </Box>
          ) : (
            <Stack direction="row" spacing={1.5} alignItems="center" sx={{ py: 6 }}>
              <CircularProgress size={20} />
              <Typography variant="body2" color="text.secondary">Waiting for the QR code…</Typography>
            </Stack>
          )}
          <Typography variant="caption" color="text.secondary" sx={{ textAlign: "center" }}>
            The code refreshes on its own. This switches to Connected once your phone pairs.
          </Typography>
          <Button onClick={ch.disconnect} color="error" startIcon={<LogoutIcon />}>
            Cancel pairing
          </Button>
        </Stack>
      ) : (
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            Get scout, download, and upload alerts on WhatsApp — and chat with ViralMint
            straight from your phone. Pairs in seconds, just like WhatsApp Web.
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Click Show QR code, then open WhatsApp → Settings → Linked Devices → Link a
            Device to scan it.
          </Typography>
          <ConnectButton
            meta={meta} onClick={ch.connect} busy={ch.saving}
            disabled={ch.saving} startIcon={<QrCodeIcon />}
          >
            {ch.saving ? "Generating QR…" : "Show QR code"}
          </ConnectButton>
        </Stack>
      )}
    />
  )
}

function DiscordBody({ meta, ch, onRefresh }) {
  return (
    <ChannelPanel
      brandColor={meta.brand} brandHoverColor={meta.brandHover}
      isConnected={ch.state === DC_STATE.CONNECTED || ch.state === DC_STATE.RECONNECTING}
      isAwaiting={ch.state === DC_STATE.AWAITING_DM}
      testing={ch.testing} onTest={ch.test} onDisconnect={ch.disconnect} onRefresh={onRefresh}
      unavailableSlot={ch.state === DC_STATE.UNAVAILABLE
        ? <MissingPackage pkg="discord.py" error={ch.info.error} /> : null}
      connectedSlot={ch.state === DC_STATE.RECONNECTING ? <ReconnectingNote /> :
        <Alert severity="success" variant="outlined">
          Connected as <strong>{ch.info.bot_username}</strong>. DM your bot on Discord to chat
          with ViralMint; notifications arrive in the same thread.
        </Alert>
      }
      awaitingSlot={
        <Alert severity="info" variant="outlined" icon={false}>
          <Stack spacing={1.25}>
            <Typography variant="body2">
              Bot online as <strong>{ch.info.bot_username}</strong>.
              {ch.info.bot_invite_url && (
                <>
                  {" "}
                  <Link href={ch.info.bot_invite_url} target="_blank" rel="noreferrer" sx={{ fontWeight: 600 }}>
                    Invite it to a server
                  </Link>
                  {" "}if you haven't yet, then
                </>
              )}
              {" "}DM the bot this pairing code:
            </Typography>
            <PairCode code={ch.info.pair_code} />
            <Typography variant="caption" color="text.secondary">{PRIVATE_NOTE}</Typography>
          </Stack>
        </Alert>
      }
      defaultSlot={
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            Create a bot at{" "}
            <Link href="https://discord.com/developers/applications" target="_blank" rel="noreferrer">
              discord.com/developers/applications
            </Link>
            : click <strong>New Application</strong>, then <strong>Bot</strong>, copy the token and
            paste it below. DMs work without any privileged intents.
          </Typography>
          <TokenField
            label="Bot token"
            placeholder="MTI..."
            value={ch.tokens.bot_token}
            onChange={(e) => ch.setToken("bot_token", e.target.value)}
            disabled={ch.saving}
          />
          <ConnectButton
            meta={meta} onClick={ch.connect} busy={ch.saving}
            disabled={ch.saving || !ch.tokens.bot_token.trim()}
          >
            {ch.saving ? "Connecting…" : "Connect Discord"}
          </ConnectButton>
        </Stack>
      }
    />
  )
}

function SlackBody({ meta, ch, onRefresh }) {
  return (
    <ChannelPanel
      brandColor={meta.brand} brandHoverColor={meta.brandHover}
      isConnected={ch.state === SL_STATE.CONNECTED}
      isAwaiting={ch.state === SL_STATE.AWAITING_DM}
      testing={ch.testing} onTest={ch.test} onDisconnect={ch.disconnect} onRefresh={onRefresh}
      unavailableSlot={ch.state === SL_STATE.UNAVAILABLE
        ? <MissingPackage pkg="slack-sdk" error={ch.info.error} /> : null}
      connectedSlot={
        <Alert severity="success" variant="outlined">
          Connected to <strong>{ch.info.team_name || "your Slack workspace"}</strong>. DM your
          bot in Slack to chat with ViralMint; notifications arrive in the same thread.
        </Alert>
      }
      awaitingSlot={
        <Alert severity="info" variant="outlined" icon={false}>
          <Stack spacing={1.25}>
            <Typography variant="body2">
              Bot online{ch.info.team_name ? ` in ${ch.info.team_name}` : ""}. Open Slack, find
              your bot in the sidebar and DM it this pairing code:
            </Typography>
            <PairCode code={ch.info.pair_code} />
            <Typography variant="caption" color="text.secondary">{PRIVATE_NOTE}</Typography>
          </Stack>
        </Alert>
      }
      defaultSlot={
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            Create a Slack app at{" "}
            <Link href="https://api.slack.com/apps" target="_blank" rel="noreferrer">api.slack.com/apps</Link>.
            Enable <strong>Socket Mode</strong>, generate an app-level token with{" "}
            <code>connections:write</code>, and install the bot to your workspace with the scopes{" "}
            <code>chat:write</code>, <code>im:history</code>, <code>im:read</code>,{" "}
            <code>im:write</code> and <code>users:read</code>. Then subscribe to the{" "}
            <code>message.im</code> event.
          </Typography>
          <TokenField
            label="Bot token (xoxb-…)"
            placeholder="xoxb-..."
            value={ch.tokens.bot_token}
            onChange={(e) => ch.setToken("bot_token", e.target.value)}
            disabled={ch.saving}
          />
          <TokenField
            label="App-level token (xapp-…)"
            placeholder="xapp-..."
            value={ch.tokens.app_token}
            onChange={(e) => ch.setToken("app_token", e.target.value)}
            disabled={ch.saving}
          />
          <ConnectButton
            meta={meta} onClick={ch.connect} busy={ch.saving}
            disabled={ch.saving || !ch.tokens.bot_token.trim() || !ch.tokens.app_token.trim()}
          >
            {ch.saving ? "Connecting…" : "Connect Slack"}
          </ConnectButton>
        </Stack>
      }
    />
  )
}

const BODIES = { telegram: TelegramBody, whatsapp: WhatsAppBody, discord: DiscordBody, slack: SlackBody }

/** The setup body for one app, chosen by key. */
export function ChannelBody({ meta, ch, onRefresh }) {
  const Body = BODIES[meta.key]
  return <Body meta={meta} ch={ch} onRefresh={onRefresh} />
}
