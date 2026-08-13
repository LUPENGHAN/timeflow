import { describe, expect, it, vi } from 'vitest';

import type {
  AssistantClientMessage,
  AssistantServerMessage,
} from '../../src/contracts/conversation';
import { AssistantContinuousConversationService } from '../../src/features/assistant/application/AssistantContinuousConversationService';
import type { AssistantAudioPlaybackPort } from '../../src/features/assistant/application/interfaces/AssistantAudioPlaybackPort';
import type { AudioCapturePort } from '../../src/features/assistant/application/interfaces/AudioCapturePort';
import type { LocalScheduleWriterPort } from '../../src/features/assistant/application/interfaces/LocalScheduleWriterPort';
import type {
  VoiceTransportConnection,
  VoiceTransportPort,
} from '../../src/features/assistant/application/interfaces/VoiceTransportPort';
import type { LocationProvider } from '../../src/infrastructure/location/LocationProvider';

class FakeConnection implements VoiceTransportConnection {
  readonly sent: AssistantClientMessage[] = [];
  closed = false;
  private readonly messageHandlers = new Set<(message: AssistantServerMessage) => void>();

  send(message: AssistantClientMessage): void {
    this.sent.push(message);
  }

  sendAudioFrame(): void {}

  onMessage(handler: (message: AssistantServerMessage) => void): () => void {
    this.messageHandlers.add(handler);
    return () => this.messageHandlers.delete(handler);
  }

  onAudioFrame(): () => void {
    return () => {};
  }

  onClose(): () => void {
    return () => {};
  }

  close(): void {
    this.closed = true;
  }

  emit(message: AssistantServerMessage): void {
    for (const handler of this.messageHandlers) handler(message);
  }

  sentOfType<T extends AssistantClientMessage['type']>(
    type: T,
  ): Extract<AssistantClientMessage, { type: T }> | undefined {
    return this.sent.find((message) => message.type === type) as
      | Extract<AssistantClientMessage, { type: T }>
      | undefined;
  }
}

class FakeTransport implements VoiceTransportPort {
  readonly connection = new FakeConnection();

  async connect(): Promise<VoiceTransportConnection> {
    return this.connection;
  }
}

class FakeCapture implements AudioCapturePort {
  started = false;
  stopped = false;

  async requestPermission(): Promise<boolean> {
    return true;
  }

  async start(): Promise<void> {
    this.started = true;
  }

  async stop(): Promise<void> {
    this.stopped = true;
  }
}

class FakePlayback implements AssistantAudioPlaybackPort {
  stopCalls = 0;

  async startStream(): Promise<void> {}

  async pushChunk(): Promise<void> {}

  async endStream(): Promise<void> {}

  async stop(): Promise<void> {
    this.stopCalls += 1;
  }
}

class FakeLocalScheduleWriter implements LocalScheduleWriterPort {
  async applyCommandResult(): Promise<void> {}
}

class FakeLocation implements LocationProvider {
  async getCurrentSample() {
    return null;
  }
}

function buildService() {
  const transport = new FakeTransport();
  const capture = new FakeCapture();
  const playback = new FakePlayback();
  const service = new AssistantContinuousConversationService(
    { accessToken: 'token', accountId: 'acc-1', deviceId: 'device-1', wsUrl: 'ws://test' },
    {
      capture,
      localScheduleWriter: new FakeLocalScheduleWriter(),
      location: new FakeLocation(),
      playback,
      transport,
    },
  );
  return { capture, playback, service, transport };
}

/** 走完一次 startTurn() 的握手：session.ready → voice.stream.started。 */
async function openListening(transport: FakeTransport, service: AssistantContinuousConversationService) {
  const startPromise = service.startTurn();
  await vi.waitFor(() => expect(transport.connection.sentOfType('session.hello')).toBeDefined());
  transport.connection.emit({
    ok: true,
    payload: { server_time: 'now', session_id: 'session-1' },
    type: 'session.ready',
  });
  await vi.waitFor(() => expect(transport.connection.sentOfType('voice.stream.start')).toBeDefined());
  transport.connection.emit({
    ok: true,
    payload: { conversation_id: 'conv-1', stream_id: 'stream-1' },
    type: 'voice.stream.started',
  });
  await startPromise;
}

describe('AssistantContinuousConversationService', () => {
  it('sends voice_mode: continuous on hello and reaches listening once the stream opens', async () => {
    const { service, transport } = buildService();
    await openListening(transport, service);

    const hello = transport.connection.sentOfType('session.hello');
    expect(hello?.payload.voice_mode).toBe('continuous');
    expect(service.getState()).toEqual({ conversationId: 'conv-1', phase: 'listening' });
  });

  it('returns to listening (not idle) after each of two voice.command.result turns', async () => {
    const { service, transport } = buildService();
    await openListening(transport, service);

    transport.connection.emit({
      conversation_id: 'conv-1',
      message_id: 'msg-1',
      payload: { operation: 'create_schedule', status: 'applied' },
      type: 'voice.command.result',
    });
    await vi.waitFor(() => expect(service.getState().phase).toBe('listening'));
    expect(service.getState()).toEqual({ conversationId: 'conv-1', phase: 'listening' });

    transport.connection.emit({
      conversation_id: 'conv-1',
      message_id: 'msg-2',
      payload: { operation: 'update_schedule', status: 'applied' },
      type: 'voice.command.result',
    });
    await vi.waitFor(() => expect(service.getState().phase).toBe('listening'));
    expect(service.getState()).toEqual({ conversationId: 'conv-1', phase: 'listening' });

    const acks = transport.connection.sent.filter((message) => message.type === 'message.ack');
    expect(acks).toHaveLength(2);
  });

  it('discards buffered audio and moves to interrupted on voice.tts.canceled', async () => {
    const { playback, service, transport } = buildService();
    await openListening(transport, service);

    transport.connection.emit({
      audio_id: 'audio-1',
      conversation_id: 'conv-1',
      payload: {
        format: 'pcm_s16le',
        purpose: 'reply',
        sample_rate_hz: 16000,
        speech_text: '好的',
      },
      type: 'voice.tts.start',
    });
    expect(service.getState()).toEqual({ conversationId: 'conv-1', phase: 'speaking' });

    transport.connection.emit({
      audio_id: 'audio-1',
      conversation_id: 'conv-1',
      type: 'voice.tts.canceled',
    });

    await vi.waitFor(() => expect(playback.stopCalls).toBe(1));
    expect(service.getState()).toEqual({ conversationId: 'conv-1', phase: 'interrupted' });
  });

  it('closes the microphone and the stream on endTurn', async () => {
    const { capture, service, transport } = buildService();
    await openListening(transport, service);
    const sentBeforeEndTurn = transport.connection.sent.length;

    await service.endTurn();

    expect(capture.stopped).toBe(true);
    expect(transport.connection.sent.slice(sentBeforeEndTurn)).toEqual([
      { payload: { stream_id: 'stream-1' }, type: 'voice.stream.end' },
    ]);
    expect(transport.connection.closed).toBe(true);
    expect(service.getState()).toEqual({ phase: 'idle' });
  });
});
