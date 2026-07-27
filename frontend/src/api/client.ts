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

export type RepeatRule = {
  id: string;
  pattern: string;
  weekdays: number[];
  time_of_day: string | null;
  series_status: string;
};

export type LocalCache = {
  items: Item[];
  reminders: Reminder[];
  places: Place[];
  write_requests: WriteRequest[];
};

export type HealthResponse = {
  status: 'ok';
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

export function listItems() {
  return apiFetch<Item[]>('/items');
}

export function applyReminderAction(
  reminderId: string,
  input: {
    action:
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
  pattern: string;
  weekdays?: number[];
  time_of_day?: string | null;
  series_status?: string;
}) {
  return apiFetch<{ repeat_rule: RepeatRule }>('/repeat-rules', {
    body: JSON.stringify(input),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
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

export { API_BASE_URL };
