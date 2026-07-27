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
  }[];
};

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

export function listItems() {
  return apiFetch<Item[]>('/items');
}

export { API_BASE_URL };
