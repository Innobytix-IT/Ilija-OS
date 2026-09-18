/**
 * Ilija WhatsApp Bridge – Baileys
 * Verbindet WhatsApp (via Baileys-Protokoll) mit Ilija's API.
 * Kein Browser nötig. Nachrichten kommen als Events, nicht per Polling.
 */

const {
    makeWASocket,
    useMultiFileAuthState,
    DisconnectReason,
    fetchLatestBaileysVersion,
    isJidGroup,
} = require('@whiskeysockets/baileys')
const axios  = require('axios')
const pino   = require('pino')
const path   = require('path')

const ILIJA_BASE   = process.env.ILIJA_BASE || 'http://localhost:5001'
const ILIJA_API    = process.env.ILIJA_API  || ILIJA_BASE + '/api/whatsapp'
const ILIJA_STATUS = ILIJA_BASE + '/api/whatsapp/connection-status'
const AUTH_DIR     = process.env.AUTH_DIR   || path.join(__dirname, 'auth_info')
const LOG_LEVEL    = process.env.LOG_LEVEL  || 'silent'
const GRUPPEN      = process.env.GRUPPEN === 'true'

async function reportStatus(status, extra = {}) {
    try { await axios.post(ILIJA_STATUS, { status, ...extra }, { timeout: 3000 }) } catch (_) {}
}

const logger = pino({ level: LOG_LEVEL })

// Einfache Deduplizierung: letzte N Message-IDs merken
const seenIds = new Set()
function alreadySeen(id) {
    if (seenIds.has(id)) return true
    seenIds.add(id)
    if (seenIds.size > 500) {
        const first = seenIds.values().next().value
        seenIds.delete(first)
    }
    return false
}

async function startBridge() {
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR)
    const { version }          = await fetchLatestBaileysVersion()

    console.log(`[Bridge] Baileys v${version.join('.')} | Ilija API: ${ILIJA_API}`)

    const sock = makeWASocket({
        version,
        auth:               state,
        logger,
        printQRInTerminal:  false,
        browser:            ['Ilija OS', 'Chrome', '1.0'],
        syncFullHistory:    false,
    })

    sock.ev.on('creds.update', saveCreds)

    sock.ev.on('connection.update', ({ connection, lastDisconnect, qr }) => {
        if (qr) {
            console.log('[Bridge] QR-Code erschienen – bitte unter http://localhost:5001/whatsapp scannen')
            reportStatus('qr', { qr })
        }
        if (connection === 'open') {
            console.log('[Bridge] ✅ WhatsApp verbunden')
            reportStatus('connected')
        }
        if (connection === 'close') {
            const code   = lastDisconnect?.error?.output?.statusCode
            const logout = code === DisconnectReason.loggedOut
            console.log(`[Bridge] Verbindung getrennt (Code ${code}). Wiederverbinden: ${!logout}`)
            reportStatus('disconnected')
            if (!logout) {
                setTimeout(startBridge, 3000)
            } else {
                console.log('[Bridge] ❌ Ausgeloggt – QR unter http://localhost:5001/whatsapp scannen')
            }
        }
    })

    sock.ev.on('messages.upsert', async ({ messages, type }) => {
        if (type !== 'notify') return

        for (const msg of messages) {
            // Eigene Nachrichten ignorieren
            if (msg.key.fromMe) continue
            if (!msg.message)   continue

            const jid = msg.key.remoteJid || ''

            // Gruppenfilter
            if (isJidGroup(jid) && !GRUPPEN) continue

            // Text extrahieren (Text, ExtendedText, Buttons, Liste)
            const m    = msg.message
            const text = (
                m.conversation
                || m.extendedTextMessage?.text
                || m.buttonsResponseMessage?.selectedButtonId
                || m.listResponseMessage?.singleSelectReply?.selectedRowId
                || ''
            ).trim()

            if (!text) continue

            // Deduplizierung
            const msgId = msg.key.id
            if (msgId && alreadySeen(msgId)) continue

            // Absendername
            const pushName = msg.pushName || jid.split('@')[0] || 'Unbekannt'

            console.log(`[Bridge] 📨 ${pushName} (${jid}): ${text.substring(0, 60)}`)

            // An Ilija schicken
            try {
                const res = await axios.post(
                    ILIJA_API,
                    { from: jid, name: pushName, text },
                    { timeout: 45000 }
                )
                const reply = (res.data.reply || '').trim()
                if (!reply) continue

                await sock.sendMessage(jid, { text: reply })
                console.log(`[Bridge] 🤖 Ilija → ${pushName}: ${reply.substring(0, 60)}`)

            } catch (err) {
                const detail = err.response?.data || err.message
                console.error(`[Bridge] ❌ Ilija API Fehler: ${detail}`)
            }
        }
    })

    return sock
}

startBridge().catch(err => {
    console.error('[Bridge] Startfehler:', err)
    process.exit(1)
})
