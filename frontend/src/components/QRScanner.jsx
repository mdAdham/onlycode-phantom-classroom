import { useEffect, useRef, useState } from 'react'
import { Html5Qrcode } from 'html5-qrcode'
import { LoaderCircle, QrCode } from 'lucide-react'

export default function QRScanner({ sessionId, onResult, onError }) {
  const [starting, setStarting] = useState(true)
  const handlers = useRef({ onResult, onError })
  useEffect(() => {
    handlers.current = { onResult, onError }
  }, [onResult, onError])

  useEffect(() => {
    const scanner = new Html5Qrcode('qr-reader')
    let mounted = true
    scanner.start(
      { facingMode: 'environment' },
      { fps: 10, qrbox: { width: 220, height: 220 } },
      (text) => {
        try {
          const scanned = JSON.parse(text)
          if (Number(scanned.session_id) === Number(sessionId) && scanned.token) {
            handlers.current.onResult(scanned.token)
          } else {
            handlers.current.onError('That QR code does not match the selected class session.')
          }
        } catch {
          handlers.current.onError('QR code format is not recognized.')
        }
      },
    ).then(() => {
      if (mounted) setStarting(false)
    }).catch((error) => {
      if (mounted) {
        setStarting(false)
        handlers.current.onError(`Camera could not start: ${error}`)
      }
    })
    return () => {
      mounted = false
      scanner.stop().catch(() => {})
    }
  }, [sessionId])

  return <div className="qr-reader-wrap">
    {starting && <div className="scanner-loading"><LoaderCircle className="spin" size={16} /> Starting camera…</div>}
    <div id="qr-reader" />
    {!starting && <span className="scanner-hint"><QrCode size={13} /> Align the active session QR code in the frame.</span>}
  </div>
}
