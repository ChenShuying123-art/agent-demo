/**
 * 后端调用统一封装（spec §9.1：所有 fetch 都写在这里，组件里不散写）。
 *
 * 约定：
 * - 后端所有错误都是 {error: {code, message}} 信封（spec §8），这里统一解包成 ApiError 抛出，
 *   组件只需要 try/catch 一次，就能拿到可读的 message 和用于判断的 code。
 * - 类型与 api/schemas.py 中的响应模型一一对应，改后端字段时这里要同步。
 */

/** 切分片段（对应后端 ChunkOut） */
export interface Chunk {
  chunk_id: string
  doc_id: string
  filename: string
  index: number
  text: string
  start: number
  end: number
}

/** 召回阶段的单条结果（cosine 分数） */
export interface SearchResult {
  chunk: Chunk
  score: number
  rank: number
}

/** 重排阶段的单条结果（rerank 分数；original_rank 用于画升降箭头） */
export interface RerankResult {
  chunk: Chunk
  rerank_score: number
  original_rank: number
  new_rank: number
  degraded: boolean
}

/** 文档元数据（对应后端 DocumentOut） */
export interface DocumentItem {
  doc_id: string
  filename: string
  path: string
  size: number
  uploaded_at: string
  indexed: boolean
  chunk_count: number
}

/** 一次问答的完整结果（对应后端 QAResultOut） */
export interface QAResult {
  answer: string
  style: string
  citations: string[]
  candidates: SearchResult[]
  used: RerankResult[]
  latency_ms: number
}

/** /api/retrieve 的响应 */
export interface RetrieveResult {
  candidates: SearchResult[]
  used: RerankResult[]
  degraded: boolean
}

/** /api/health 的响应 */
export interface Health {
  status: string
  chat_model: string
  embedding_model: string
  rerank_model: string
}

/** /api/index 的单篇结果 */
export interface IndexReport {
  doc_id: string
  chunks: number
  ms: number
}

/** 三种提示词风格（与后端 prompts.PROMPT_STYLES 一致，顺序也一致） */
export const PROMPT_STYLES = ['strict_citation', 'concise_assistant', 'socratic_guide'] as const
export type PromptStyle = (typeof PROMPT_STYLES)[number]

/** 风格 key → 中文展示名 */
export const STYLE_LABELS: Record<string, string> = {
  strict_citation: '严谨引用型',
  concise_assistant: '简洁助手型',
  socratic_guide: '引导启发型',
}

/** 提问参数（AskPanel 提交上来） */
export interface AskOptions {
  question: string
  style: string // 三种风格之一，或 "all" 表示全部对比
  useRerank: boolean
}

/** 浏览器的原始输入上限，避免把超长文本发给后端 */
const MAX_QUESTION_LEN = 1000

/** 后端错误：保留 code 便于组件区分（如 network_error / invalid_request / 502 的原始 code） */
export class ApiError extends Error {
  code: string

  constructor(code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.code = code
  }
}

/** 所有请求统一走这里：拼前缀、解信封、抛 ApiError */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response
  try {
    resp = await fetch(`/api${path}`, init)
  } catch (err) {
    // fetch 抛错说明连后端都没连上（未启动 / 代理没配好），给一句人话
    throw new ApiError('network_error', `无法连接后端：${(err as Error).message}`)
  }

  const text = await resp.text()
  let data: unknown = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      // 后端返回了非 JSON（例如网关的 HTML 错误页），别让解析异常盖住真正的问题
      throw new ApiError(String(resp.status), `后端返回了非 JSON 响应（HTTP ${resp.status}）`)
    }
  }

  if (!resp.ok) {
    const envelope = (data as { error?: { code?: string; message?: string } } | null)?.error
    throw new ApiError(
      envelope?.code ?? String(resp.status),
      envelope?.message ?? resp.statusText ?? `请求失败（HTTP ${resp.status}）`,
    )
  }
  return data as T
}

function jsonBody(payload: unknown): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }
}

/** 去掉空字符串后的 doc_ids；为空则传 undefined（后端按"全库"处理） */
function cleanDocIds(docIds: string[]): string[] | undefined {
  return docIds.length > 0 ? docIds : undefined
}

export const api = {
  /** 自检：回显三个模型名 */
  health(): Promise<Health> {
    return request<Health>('/health')
  },

  /** 列出全部文档（含 indexed / chunk_count） */
  listDocuments(): Promise<DocumentItem[]> {
    return request<DocumentItem[]>('/documents')
  },

  /** 上传文档（multipart）。重复内容后端会返回已有记录 */
  uploadDocument(file: File): Promise<DocumentItem> {
    const form = new FormData()
    form.append('file', file)
    // 注意：不要手动设 Content-Type，浏览器需要自己加 multipart 的 boundary
    return request<DocumentItem>('/documents', { method: 'POST', body: form })
  },

  /** 删除文档（连同其 chunk 向量） */
  deleteDocument(docId: string): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>(`/documents/${encodeURIComponent(docId)}`, { method: 'DELETE' })
  },

  /** 向量化指定文档 */
  indexDocuments(docIds: string[]): Promise<IndexReport[]> {
    return request<IndexReport[]>('/index', jsonBody({ doc_ids: docIds }))
  },

  /** 观测两阶段检索（前端"召回 → 重排"面板的数据来源） */
  retrieve(question: string, docIds: string[], useRerank: boolean): Promise<RetrieveResult> {
    return request<RetrieveResult>(
      '/retrieve',
      jsonBody({ question, doc_ids: cleanDocIds(docIds), use_rerank: useRerank }),
    )
  },

  /** 单风格问答 */
  ask(question: string, style: string, docIds: string[], useRerank: boolean): Promise<QAResult> {
    return request<QAResult>(
      '/qa',
      jsonBody({
        question: question.slice(0, MAX_QUESTION_LEN),
        style,
        doc_ids: cleanDocIds(docIds),
        use_rerank: useRerank,
      }),
    )
  },

  /** 一次性拿三种风格（便于并排对比） */
  askAllStyles(question: string, docIds: string[]): Promise<QAResult[]> {
    return request<QAResult[]>(
      '/qa/compare',
      jsonBody({ question: question.slice(0, MAX_QUESTION_LEN), doc_ids: cleanDocIds(docIds) }),
    )
  },
}
