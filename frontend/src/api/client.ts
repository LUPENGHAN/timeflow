import { Platform } from 'react-native';

const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://127.0.0.1:8000/api/v1';

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);

  if (!response.ok) {
    throw new Error(`API request failed with status ${response.status}`);
  }

  return (await response.json()) as T;
}

export type EventMessage = {
  event_id: string;
  event_type: string;
  aggregate_type: string;
  aggregate_id: string;
  version: number;
  occurred_at: string;
  payload: Record<string, unknown>;
};

export type WriteRequest = {
  id: string;
  source_command_id: string;
  status: string;
  candidate_payload: Record<string, unknown>;
  payload_hash: string;
  expires_at: string;
  created_at: string;
};

export type VoiceCommandResult = {
  voice_command: {
    id: string;
    transcript: string;
    status: string;
    command_id: string | null;
    created_at: string;
  };
  write_request: WriteRequest | null;
  events: EventMessage[];
  clarification: string | null;
  candidates: Item[];
};

export type Item = {
  id: string;
  type: 'calendar_event' | 'todo';
  title: string;
  description: string | null;
  status: string;
  start_at: string | null;
  end_at: string | null;
  due_at: string | null;
  place_text: string | null;
  version: number;
  updated_at: string;
  reminders: {
    id: string;
    item_id: string;
    trigger_type: string;
    trigger_at: string | null;
    place_id: string | null;
    priority: string;
    delivery_channel: string;
    status: string;
    snooze_count: number;
    local_notification_id: string | null;
    local_registration_status: string;
    failed_reason: string | null;
    fallback_status: string;
    fallback_after_seconds: number;
    fallback_requested_at: string | null;
    version: number;
  }[];
};

export type Reminder = Item['reminders'][number];

export type Place = {
  id: string;
  label: string;
  place_type: 'home' | 'work' | 'custom' | 'temporary_parking';
  latitude: string | null;
  longitude: string | null;
  accuracy_meters: number | null;
  radius_meters: number;
  description: string | null;
};

export type RepeatPattern = 'daily' | 'weekdays' | 'custom_weekdays';
export type RepeatSeriesStatus = 'active' | 'paused' | 'stopped';

export type RepeatRule = {
  id: string;
  pattern: RepeatPattern;
  weekdays: number[];
  time_of_day: string | null;
  series_status: RepeatSeriesStatus;
};

export type LocalCache = {
  items: Item[];
  reminders: Reminder[];
  places: Place[];
  repeat_rules: RepeatRule[];
  outbox_messages: OutboxMessage[];
  write_requests: WriteRequest[];
  sync_cursor: number;
};

const LOCAL_CACHE_KEY = 'timeflow.local-cache.v1';
const OFFLINE_WRITE_QUEUE_KEY = 'timeflow.offline-write-queue.v1';

export type OfflineWriteRequestDraft = {
  candidate_payload: Record<string, unknown>;
  source_command_id: string;
};

export type OfflineWriteRequest = OfflineWriteRequestDraft & {
  created_at: string;
  id: string;
};

export function readLocalCache(): LocalCache | null {
  if (typeof globalThis.localStorage === 'undefined') {
    return null;
  }

  try {
    const raw = globalThis.localStorage.getItem(LOCAL_CACHE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as Partial<LocalCache>;
    return {
      items: Array.isArray(parsed.items) ? parsed.items : [],
      reminders: Array.isArray(parsed.reminders) ? parsed.reminders : [],
      outbox_messages: Array.isArray(parsed.outbox_messages) ? parsed.outbox_messages : [],
      places: Array.isArray(parsed.places) ? parsed.places : [],
      repeat_rules: Array.isArray(parsed.repeat_rules) ? parsed.repeat_rules : [],
      sync_cursor: typeof parsed.sync_cursor === 'number' ? parsed.sync_cursor : 0,
      write_requests: Array.isArray(parsed.write_requests) ? parsed.write_requests : [],
    };
  } catch {
    return null;
  }
}

export function writeLocalCache(cache: LocalCache) {
  if (typeof globalThis.localStorage === 'undefined') {
    return;
  }

  try {
    globalThis.localStorage.setItem(LOCAL_CACHE_KEY, JSON.stringify(cache));
  } catch {
    // Cache is best-effort only.
  }
}

export function readOfflineWriteQueue(): OfflineWriteRequest[] {
  if (typeof globalThis.localStorage === 'undefined') {
    return [];
  }

  try {
    const raw = globalThis.localStorage.getItem(OFFLINE_WRITE_QUEUE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter(isOfflineWriteRequest);
  } catch {
    return [];
  }
}

export function writeOfflineWriteQueue(queue: OfflineWriteRequest[]) {
  if (typeof globalThis.localStorage === 'undefined') {
    return;
  }

  try {
    globalThis.localStorage.setItem(OFFLINE_WRITE_QUEUE_KEY, JSON.stringify(queue));
  } catch {
    // Queue is best-effort only.
  }
}

export function enqueueOfflineWriteRequest(draft: OfflineWriteRequestDraft) {
  const entry: OfflineWriteRequest = {
    ...draft,
    created_at: new Date().toISOString(),
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
  };
  const queue = [...readOfflineWriteQueue(), entry];
  writeOfflineWriteQueue(queue);
  return entry;
}

function isOfflineWriteRequest(value: unknown): value is OfflineWriteRequest {
  if (!value || typeof value !== 'object') {
    return false;
  }
  const candidate = value as Partial<OfflineWriteRequest>;
  return (
    typeof candidate.id === 'string' &&
    typeof candidate.created_at === 'string' &&
    typeof candidate.source_command_id === 'string' &&
    typeof candidate.candidate_payload === 'object' &&
    candidate.candidate_payload !== null
  );
}

export type HealthResponse = {
  status: 'ok';
};

export type OutboxMessage = {
  id: string;
  event_id: string;
  channel: string;
  payload: Record<string, unknown>;
  status: string;
  attempts: number;
  created_at: string;
};

export function getHealth() {
  return apiFetch<HealthResponse>('/health');
}

export function createVoiceCommand(transcript: string) {
  return apiFetch<VoiceCommandResult>('/voice/commands', {
    body: JSON.stringify({ transcript }),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
  });
}

export async function createAudioVoiceCommand(audioUri: string) {
  const fileName = getAudioFileName(audioUri);
  const formData = new FormData();

  if (Platform.OS === 'web') {
    const audioResponse = await fetch(audioUri);
    const audioBlob = await audioResponse.blob();
    formData.append('audio', audioBlob, fileName);
  } else {
    formData.append('audio', {
      name: fileName,
      type: getAudioMimeType(fileName),
      uri: audioUri,
    } as unknown as Blob);
  }

  return apiFetch<VoiceCommandResult>('/voice/commands/audio', {
    body: formData,
    method: 'POST',
  });
}

function getAudioFileName(audioUri: string) {
  const path = audioUri.split('?')[0];
  return path.split('/').pop() || `recording-${Date.now()}.m4a`;
}

function getAudioMimeType(fileName: string) {
  const extension = fileName.split('.').pop()?.toLowerCase();
  if (extension === 'webm') {
    return 'audio/webm';
  }
  if (extension === 'wav') {
    return 'audio/wav';
  }
  if (extension === 'mp3') {
    return 'audio/mpeg';
  }
  if (extension === 'caf') {
    return 'audio/x-caf';
  }
  if (extension === '3gp') {
    return 'audio/3gpp';
  }
  return 'audio/mp4';
}

export function listPendingWriteRequests() {
  return apiFetch<WriteRequest[]>('/write-requests/pending');
}

export function confirmWriteRequest(writeRequestId: string) {
  return apiFetch<{ write_request: WriteRequest; events: EventMessage[] }>(
    `/write-requests/${writeRequestId}/confirm`,
    { method: 'POST' },
  );
}

export function rejectWriteRequest(writeRequestId: string) {
  return apiFetch<{ write_request: WriteRequest; events: EventMessage[] }>(
    `/write-requests/${writeRequestId}/reject`,
    { method: 'POST' },
  );
}

export function createWriteRequest(input: {
  source_command_id: string;
  candidate_payload: Record<string, unknown>;
}) {
  return apiFetch<{ write_request: WriteRequest; events: EventMessage[] }>('/write-requests', {
    body: JSON.stringify(input),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
  });
}

export function updateWriteRequest(
  writeRequestId: string,
  input: {
    candidate_payload: Record<string, unknown>;
  },
) {
  return apiFetch<{ write_request: WriteRequest; events: EventMessage[] }>(
    `/write-requests/${writeRequestId}`,
    {
      body: JSON.stringify(input),
      headers: { 'Content-Type': 'application/json' },
      method: 'PATCH',
    },
  );
}

export function listItems() {
  return apiFetch<Item[]>('/items');
}

export function updateItem(
  itemId: string,
  input: {
    title?: string | null;
    description?: string | null;
    start_at?: string | null;
    end_at?: string | null;
    due_at?: string | null;
    place_text?: string | null;
  },
) {
  return apiFetch<{ item: Item; events: EventMessage[] }>(`/items/${itemId}`, {
    body: JSON.stringify(input),
    headers: { 'Content-Type': 'application/json' },
    method: 'PATCH',
  });
}

export function completeItem(itemId: string) {
  return apiFetch<{ item: Item; events: EventMessage[] }>(`/items/${itemId}/complete`, {
    method: 'POST',
  });
}

export function cancelCompleteItem(itemId: string) {
  return apiFetch<{ item: Item; events: EventMessage[] }>(`/items/${itemId}/cancel-complete`, {
    method: 'POST',
  });
}

export function deleteItem(itemId: string) {
  return apiFetch<{ item: Item; events: EventMessage[] }>(`/items/${itemId}`, {
    method: 'DELETE',
  });
}

export function listOutboxMessages() {
  return apiFetch<OutboxMessage[]>('/events/outbox');
}

export function listReminders() {
  return apiFetch<Reminder[]>('/reminders');
}

export function applyReminderAction(
  reminderId: string,
  input: {
    action:
      | 'armed'
      | 'registered'
      | 'delivered'
      | 'failed'
      | 'registration_failed'
      | 'local_unavailable'
      | 'snooze'
      | 'dismiss'
      | 'cancel';
    failed_reason?: string | null;
    local_notification_id?: string | null;
    snooze_minutes?: number;
    fallback_after_seconds?: number;
  },
) {
  return apiFetch<{ reminder: Reminder; events: EventMessage[] }>(
    `/reminders/${reminderId}/actions`,
    {
      body: JSON.stringify(input),
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
    },
  );
}

export function createReminder(input: {
  item_id: string;
  trigger_type: 'time' | 'enter_place' | 'leave_place' | 'return_to_place';
  trigger_at?: string | null;
  place_id?: string | null;
  priority?: 'low' | 'normal' | 'high';
}) {
  return apiFetch<{ reminder: Reminder; events: EventMessage[] }>('/reminders', {
    body: JSON.stringify(input),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
  });
}

export function listPlaces() {
  return apiFetch<Place[]>('/places');
}

export function createPlace(input: {
  label: string;
  place_type: 'home' | 'work' | 'custom' | 'temporary_parking';
  radius_meters?: number;
  description?: string | null;
  latitude?: string | null;
  longitude?: string | null;
  accuracy_meters?: number | null;
}) {
  return apiFetch<{ place: Place }>('/places', {
    body: JSON.stringify(input),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
  });
}

export function listRepeatRules() {
  return apiFetch<RepeatRule[]>('/repeat-rules');
}

export function createRepeatRule(input: {
  pattern: RepeatPattern;
  weekdays?: number[];
  time_of_day: string;
  series_status?: RepeatSeriesStatus;
}) {
  return apiFetch<{ repeat_rule: RepeatRule }>('/repeat-rules', {
    body: JSON.stringify(input),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
  });
}

export function deletePlace(placeId: string) {
  return apiFetch<{ place: Place }>(`/places/${placeId}`, {
    method: 'DELETE',
  });
}

export function createItem(input: {
  type: 'calendar_event' | 'todo';
  title: string;
  description?: string | null;
  start_at?: string | null;
  end_at?: string | null;
  due_at?: string | null;
  place_text?: string | null;
}) {
  return apiFetch<{ item: Item; events: EventMessage[] }>('/items', {
    body: JSON.stringify(input),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
  });
}

export function degradePermission(input: {
  permission: 'microphone' | 'notification' | 'location';
  reason: string;
  title: string;
  place_text?: string | null;
}) {
  return apiFetch<{ item: Item; events: EventMessage[] }>('/permissions/degrade', {
    body: JSON.stringify(input),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
  });
}

export function getRealtimeUrl() {
  return `${API_BASE_URL.replace(/^http/, 'ws').replace(/\/$/, '')}/ws`;
}

export function getSwaggerUrl() {
  return `${API_BASE_URL.replace(/\/api\/v1$/, '')}/docs`;
}

export { API_BASE_URL };
