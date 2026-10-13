const API_BASE = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:5000/api').replace(/\/$/, '')

export async function api(path, options = {}) {
  const { body, headers, ...requestOptions } = options
  let response
  try {
    response = await fetch(`${API_BASE}${path.startsWith('/') ? path : `/${path}`}`, {
      ...requestOptions,
      headers: {
        ...(body ? { 'Content-Type': 'application/json' } : {}),
        ...headers,
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    })
  } catch {
    throw new Error('Unable to reach the backend API. Start the Flask server and try again.')
  }
  const isJson = response.headers.get('content-type')?.includes('application/json')
  if (!isJson) throw new Error(`The API returned an unexpected response (${response.status}).`)
  const result = await response.json()
  if (!response.ok || result.error) throw new Error(result.error || `Request failed (${response.status}).`)
  return result.data
}

export async function downloadReport(path) {
  let response
  try {
    response = await fetch(`${API_BASE}${path.startsWith('/') ? path : `/${path}`}`)
  } catch {
    throw new Error('Unable to reach the backend API. Start the Flask server and try again.')
  }
  if (!response.ok) {
    const result = await response.json().catch(() => null)
    throw new Error(result?.error || `CSV export failed (${response.status}).`)
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'campus-energy-report.csv'
  document.body.append(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
