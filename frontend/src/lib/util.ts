/** Copy with a textarea fallback for pages served over plain http (no Clipboard API). */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // fall back below
  }
  const area = document.createElement('textarea')
  area.value = text
  area.setAttribute('readonly', '')
  area.style.position = 'fixed'
  area.style.opacity = '0'
  document.body.appendChild(area)
  area.select()
  let ok = false
  try {
    ok = document.execCommand('copy')
  } catch {
    ok = false
  }
  document.body.removeChild(area)
  return ok
}

export function formatRemaining(expiresAt: string, now = Date.now()): string {
  const diff = new Date(expiresAt).getTime() - now
  if (Number.isNaN(diff)) return 'unknown'
  if (diff <= 0) return 'expired'
  const mins = Math.floor(diff / 60000)
  const secs = Math.floor((diff % 60000) / 1000)
  return `${mins}m ${secs}s`
}
