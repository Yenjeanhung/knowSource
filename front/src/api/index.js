const API = import.meta.env.DEV
  ? ''  // dev mode uses Vite proxy
  : 'http://localhost:8000'

export async function fetchKbs() {
  return (await (await fetch(`${API}/api/kb`)).json()) || []
}

export async function createKb(name) {
  return await (await fetch(`${API}/api/kb`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })).json()
}

export async function getKb(kbId) {
  return await (await fetch(`${API}/api/kb/${kbId}`)).json()
}

export async function deleteKb(kbId) {
  await fetch(`${API}/api/kb/${kbId}`, { method: 'DELETE' })
}

export async function updateKb(kbId, { name, description }) {
  const res = await fetch(`${API}/api/kb/${kbId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description }),
  })
  if (!res.ok) throw new Error('Update failed')
  return res.json()
}

export async function deleteFile(fileId) {
  await fetch(`${API}/api/files/${fileId}`, { method: 'DELETE' })
}

export async function processFile(fileId) {
  const res = await fetch(`${API}/api/files/${fileId}/process`, { method: 'POST' })
  if (!res.ok) throw new Error('Process failed')
  return res.json()
}

export async function getFileStatus(fileId) {
  const res = await fetch(`${API}/api/files/${fileId}/status`)
  if (!res.ok) throw new Error('Status failed')
  return res.json()
}

export async function fetchVectorRecords({ kbId = '', q = '', unsyncedOnly = false, limit = 100, offset = 0 } = {}) {
  const params = new URLSearchParams()
  if (kbId) params.set('kb_id', kbId)
  if (q) params.set('q', q)
  if (unsyncedOnly) params.set('unsynced_only', 'true')
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  const res = await fetch(`${API}/api/vector-records?${params.toString()}`)
  if (!res.ok) throw new Error('Fetch vector records failed')
  return res.json()
}

export async function fetchVectorSearchTest({ kbId, query, topK = 8 }) {
  const params = new URLSearchParams()
  params.set('kb_id', kbId)
  params.set('query', query)
  params.set('top_k', String(topK))
  const res = await fetch(`${API}/api/vector-search-test?${params.toString()}`)
  if (!res.ok) throw new Error('Fetch vector search test failed')
  return res.json()
}

export async function fetchVectorSummaryExport({ kbId = '', format = 'json' } = {}) {
  const params = new URLSearchParams()
  if (kbId) params.set('kb_id', kbId)
  params.set('format', format)
  const res = await fetch(`${API}/api/vector-summary-export?${params.toString()}`)
  if (!res.ok) throw new Error('Fetch vector summary export failed')
  if (format === 'md') return res.text()
  return res.json()
}

/**
 * 流式问答。通过回调逐 token 输出。
 * @param {string} kbId
 * @param {string} query
 * @param {(chunks: Array) => void} onChunks  检索到 chunks 时触发
 * @param {(token: string) => void} onToken   每个 token 片段时触发
 * @param {number} topK
 */
export async function queryRagStream(kbId, query, { onChunks, onToken }) {
  const res = await fetch(`${API}/api/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, kb_id: kbId }),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const payload = line.slice(6)
      if (payload === '[DONE]') return
      try {
        const data = JSON.parse(payload)
        if (data.type === 'chunks') onChunks(data.chunks)
        else if (data.type === 'token') onToken(data.content)
      } catch { /* skip malformed lines */ }
    }
  }
}

export function getFilePreviewUrl(fileId) {
  return `${API}/api/files/${fileId}/preview`
}

export async function fetchFileContent(fileId) {
  const res = await fetch(`${API}/api/files/${fileId}/preview`)
  if (!res.ok) throw new Error('Preview failed')
  return res.text()
}

export async function uploadChunk({ fileId, fileName, fileSize, kbId, chunkIndex, totalChunks, chunk }) {
  const form = new FormData()
  form.append('file_id', fileId)
  form.append('file_name', fileName)
  form.append('file_size', fileSize)
  form.append('kb_id', kbId)
  form.append('chunk_index', chunkIndex)
  form.append('total_chunks', totalChunks)
  form.append('chunk', chunk)
  const res = await fetch(`${API}/api/upload/chunk`, { method: 'POST', body: form })
  if (!res.ok) throw new Error('Upload failed')
  return res.json()
}
