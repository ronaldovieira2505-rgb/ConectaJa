export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function csrfFromCookie(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

export async function api<T>(
  path: string,
  options: { method?: string; body?: unknown; form?: FormData } = {},
): Promise<T> {
  const method = options.method ?? 'GET'
  const headers: Record<string, string> = {}
  // Com FormData o navegador define o Content-Type (multipart) sozinho.
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (method !== 'GET') headers['X-CSRFToken'] = csrfFromCookie()

  const response = await fetch(path, {
    method,
    headers,
    credentials: 'same-origin',
    body: options.form ?? (options.body !== undefined ? JSON.stringify(options.body) : undefined),
  })
  if (!response.ok) throw await errorFrom(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

async function errorFrom(response: Response): Promise<ApiError> {
  let detail = 'Não foi possível concluir a operação.'
  try {
    const data = (await response.json()) as { detail?: string }
    if (data.detail) detail = data.detail
  } catch {
    // resposta sem JSON: mantém a mensagem padrão
  }
  return new ApiError(response.status, detail)
}

/** Baixa um arquivo da API (ex.: extrato CSV). O nome vem do `Content-Disposition`. */
export async function downloadFile(
  path: string,
  fallbackName: string,
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(path, { credentials: 'same-origin' })
  if (!response.ok) throw await errorFrom(response)
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const match = disposition.match(/filename="?([^";]+)"?/)
  return { blob: await response.blob(), filename: match ? match[1] : fallbackName }
}

/** Entrega o arquivo ao navegador como download. */
export function saveFile(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export type Role = 'COMPANY' | 'WORKER' | 'ADMIN'

export interface User {
  id: number
  name: string
  email: string
  role: Role
  verification_status: string | null
}

export interface CnpjData {
  legal_name: string
  trade_name: string
  registration_status: string
  street: string
  number: string
  complement: string
  district: string
  city: string
  state: string
  zip_code: string
}

export interface CnpjLookupResult {
  found: boolean
  available: boolean
  detail?: string
  data?: CnpjData
}

export interface ProfileStep {
  key: string
  label: string
  done: boolean
  status?: string
}

export interface WorkerProfile {
  id: number
  full_name: string
  cpf: string
  phone: string
  verification_status: string
  pix_key_type?: string
  pix_key?: string
  verification_message?: string
  profile_steps: ProfileStep[]
  // Perfil completo (foto, documentos, números e avaliações).
  photo_url?: string | null
  member_since?: string
  documents?: WorkerDocumentInfo[]
  stats?: WorkerStats
  reviews?: WorkerReview[]
}

export interface AppNotification {
  id: number
  kind: string
  title: string
  message: string
  link: string
  read: boolean
  created_at: string
}

export interface NotificationList {
  unread_count: number
  results: AppNotification[]
}

export interface Vacancy {
  id: number
  title: string
  category: string
  category_label: string
  description: string
  street: string
  city: string
  state: string
  latitude: string
  longitude: string
  starts_at: string
  ends_at: string
  pay_per_person_cents: number
  positions: number
  filled_positions: number
  total_cents: number
  retained_cents: number
  status: string
  status_label: string
  payment_method?: string
  photo_url: string | null
}

/** Avaliação recebida pelo candidato (US40): sem valores nem endereço da vaga. */
export interface CandidateReview {
  rating: number
  comment: string
  created_at: string
  company_name: string
}

/** Candidato pendente: sem CPF, telefone nem PIX (US42). */
export interface Candidate {
  id: number
  name: string
  photo_url: string | null
  verified: boolean
  completed_shifts: number
  no_shows_30d?: number
  rating_avg?: number | null
  rating_count?: number
  recent_reviews?: CandidateReview[]
  applied_at: string
  // Posição na lista de espera (US43); null enquanto a equipe não está completa.
  waitlist_position?: number | null
}

/** Prestador alocado: contato liberado após a aprovação. */
export interface TeamMember {
  id: number
  first_name: string
  phone: string
  status: string
  status_label: string
}

export interface VacancyCandidates {
  positions: number
  filled_positions: number
  team_complete: boolean
  // Chamada automática da lista de espera (US43); ligada por padrão.
  auto_call_waitlist?: boolean
  free_cancel_minutes_before?: number
  no_show_window_days?: number
  candidates: Candidate[]
  team: TeamMember[]
}

export interface VacancyList {
  total_retained_cents: number
  results: Vacancy[]
}

/** Card da busca de vagas do prestador (US12/US17). */
export interface VacancyCard {
  id: number
  title: string
  company_name: string
  category: string
  category_label: string
  starts_at: string
  ends_at: string
  district: string
  city: string
  state: string
  gross_cents: number
  fee_percent: number
  fee_cents: number
  net_cents: number
  remaining_positions: number
  payment_guaranteed: boolean
  urgent: boolean
  distance_km: number | null
  photo_url: string | null
  // Média das avaliações da empresa (US64); `average` é null sem avaliações.
  company_rating?: CompanyRating
}

export interface CompanyRating {
  average: number | null
  count: number
}

/** Avaliação recebida pela empresa, com o prestador abreviado ("Ana S.") (US64). */
export interface CompanyReview {
  id: number
  rating: number
  comment: string
  created_at: string
  vacancy_title: string
  reviewer: string
}

export interface CompanyReviews {
  summary: CompanyRating
  results: CompanyReview[]
}

/** Texto da nota da empresa: "★ 4,6 · 12 avaliações" ou "Sem avaliações ainda" (US64). */
export function ratingLabel(rating?: CompanyRating): string {
  if (!rating || rating.average === null || rating.count === 0) return 'Sem avaliações ainda'
  const average = rating.average.toLocaleString('pt-BR', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })
  return `★ ${average} · ${rating.count} ${rating.count === 1 ? 'avaliação' : 'avaliações'}`
}

/** Regras da plataforma vindas de `PlatformParameters` (US16): minutos, metros, dias e contagens. */
export interface VacancyRules {
  free_cancel_minutes_before: number
  late_cancel_block_days: number
  geofence_radius_m: number
  checkin_open_minutes_before: number
  no_show_tolerance_minutes: number
  no_show_limit: number
  no_show_window_days: number
  suspension_days: number
  contest_window_minutes: number
}

/** Prazo amigável a partir de minutos: "30 min", "24 h", "2 dias", "1 h 30 min". */
export function formatMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes} min`
  if (minutes % 1440 === 0) {
    const days = minutes / 1440
    return days === 1 ? '24 h' : `${days} dias`
  }
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`
}

export function formatDays(days: number): string {
  return days === 1 ? '1 dia' : `${days} dias`
}

/** O que o prestador vê da empresa (US15): sem CNPJ, contato, endereço completo ou valores. */
export interface CompanySummary {
  id: number
  name: string
  logo_url: string | null
  district: string
  city: string
  state: string
  member_since: string
  rating: CompanyRating
  completed_shifts: number
  description: string
  profile_available: boolean
}

export interface CompanyPublicReview {
  id: number
  rating: number
  comment: string
  created_at: string
  reviewer: string
}

/** Página pública da empresa (US15). */
export interface CompanyPublicProfile extends CompanySummary {
  open_vacancies: VacancyCard[]
  recent_reviews: CompanyPublicReview[]
}

export interface VacancyPublicDetail extends VacancyCard {
  company?: CompanySummary
  rules: VacancyRules
  description: string
  street: string
  number: string
  complement: string
  zip_code: string
  latitude: string
  longitude: string
  can_apply: boolean
  apply_blocker: string | null
  my_application: { id: number; status: string; status_label: string } | null
}

/** Item de "Meus trabalhos": uma candidatura ou uma alocação (US37/US38). */
export interface JobItem {
  kind: 'application' | 'assignment'
  id: number
  vacancy_id: number
  title: string
  category: string
  photo_url: string | null
  company_name: string
  starts_at: string
  ends_at: string
  gross_cents: number
  net_cents: number
  status: string
  status_label: string
  can_withdraw: boolean
  // Candidatura pendente numa vaga com equipe completa (US43).
  waitlist_position?: number | null
  // Só nas alocações (US50/US54).
  can_check_in?: boolean
  can_check_out?: boolean
  // Cancelamento pelo prestador (US72).
  can_cancel?: boolean
  cancel_is_late?: boolean
  cancel_warning?: string
  check_in_opens_at?: string
  check_in_closes_at?: string
  check_in_at?: string | null
  check_out_at?: string | null
  check_out_auto?: boolean
  // Motivo informado pela empresa quando as horas foram contestadas (US57).
  contest_reason?: string
  // Resposta do prestador à contestação (US58): única e definitiva.
  can_respond_to_contest?: boolean
  contest_response?: string
  contest_response_at?: string | null
  // Avaliação da empresa pelo prestador (US64).
  can_review?: boolean
  review_deadline?: string | null
  my_review?: { rating: number; comment: string } | null
}

export type JobGroupKey = 'waiting' | 'upcoming' | 'in_progress' | 'completed' | 'closed'

export interface MyJobs {
  groups: Record<JobGroupKey, JobItem[]>
}

export function brl(cents: number): string {
  return (cents / 100).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' })
}

const TZ = 'America/Sao_Paulo'

/** Hora local de Brasília: "09:05". */
export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('pt-BR', { timeZone: TZ, hour: '2-digit', minute: '2-digit' })
}

/** Turno em uma linha: "3 de nov., 09:00 às 13:00" (ou com as duas datas). */
export function formatShift(startIso: string, endIso: string): string {
  const day = (iso: string) =>
    new Date(iso).toLocaleDateString('pt-BR', { timeZone: TZ, day: 'numeric', month: 'short' })
  const time = (iso: string) =>
    new Date(iso).toLocaleTimeString('pt-BR', { timeZone: TZ, hour: '2-digit', minute: '2-digit' })
  return day(startIso) === day(endIso)
    ? `${day(startIso)}, ${time(startIso)} às ${time(endIso)}`
    : `${day(startIso)} ${time(startIso)} até ${day(endIso)} ${time(endIso)}`
}

/** Alocação aguardando a conferência das horas pela empresa (US56). */
export interface PendingAssignment {
  id: number
  vacancy_id: number
  vacancy_title: string
  worker_first_name: string
  starts_at: string
  ends_at: string
  check_in_at: string | null
  check_out_at: string
  check_out_auto: boolean
  check_in_distance_m: number | null
  gross_cents: number
  auto_approve_at: string
  auto_approve_in_seconds: number
  can_contest: boolean
}

/** Alocação contestada, com o motivo da empresa e a versão do prestador (US58). */
export interface ContestedAssignment {
  id: number
  vacancy_id: number
  vacancy_title: string
  worker_first_name: string
  contest_reason: string
  contest_response: string
  contest_response_at: string | null
}

/** "dd/mm às hh:mm" em horário de Brasília, como em "enviada em 03/11 às 14:30". */
export function formatDayMonthTime(iso: string): string {
  const date = new Date(iso).toLocaleDateString('pt-BR', {
    timeZone: 'America/Sao_Paulo',
    day: '2-digit',
    month: '2-digit',
  })
  return `${date} às ${formatTime(iso)}`
}

/** "23 h 10 min" a partir de uma quantidade de segundos. */
export function formatRemaining(seconds: number): string {
  const minutes = Math.max(0, Math.floor(seconds / 60))
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return h > 0 ? `${h} h ${m} min` : `${m} min`
}

/** Item "a receber" da carteira do prestador (US60). */
export interface WalletReceivable {
  assignment_id: number
  vacancy_id: number
  title: string
  company_name: string
  starts_at: string
  ends_at: string
  status: string
  status_label: string
  net_cents: number
  expected_release_at: string | null
  release_note: string
}

/** Item já liberado (repasse) da carteira. */
export interface WalletReleased {
  assignment_id: number
  vacancy_id: number
  title: string
  company_name: string
  starts_at: string
  ends_at: string
  released_at: string
  gross_cents: number
  fee_cents: number
  net_cents: number
  pix_destination: string
}

export interface Wallet {
  totals: { receivable_cents: number; released_cents: number; fees_cents: number }
  fee_percent: number
  receivable: WalletReceivable[]
  released: WalletReleased[]
}

export interface WorkerDocumentInfo {
  kind: string
  label: string
  uploaded: boolean
  url: string | null
}

export interface WorkerStats {
  completed_shifts: number
  total_received_cents: number
  rating_average: number | null
  rating_count: number
}

export interface WorkerReview {
  id: number
  rating: number
  comment: string
  company_name: string
  vacancy_title: string
  created_at: string
}

export interface CompanyStats {
  published_vacancies: number
  finished_vacancies: number
  completed_shifts: number
  total_paid_cents: number
}

/** Perfil da empresa: cadastro verificado, apresentação, logo e números. */
export interface CompanyProfile {
  id: number
  name: string
  legal_name: string
  trade_name: string
  cnpj: string
  state_registration: string
  tax_regime_label: string
  registration_status: string
  street: string
  number: string
  complement: string
  district: string
  city: string
  state: string
  zip_code: string
  phone: string
  payment_method_label: string
  verification_status: string
  verification_label: string
  description: string
  logo_url: string | null
  member_since: string
  stats: CompanyStats
}

/** "nov. de 2026": desde quando a conta existe. */
export function formatMonthYear(iso: string): string {
  return new Date(iso).toLocaleDateString('pt-BR', { month: 'short', year: 'numeric' })
}

export function formatCnpj(cnpj: string): string {
  return cnpj.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5')
}
