import { isTransportError, type AssistantServerMessage } from '../../../contracts/conversation';
import type { AppliedCommand, ConversationTurnState } from '../domain/ConversationTurn';

import type {
  AssistantApplicationDependencies,
  AssistantApplicationOptions,
  AssistantApplicationPort,
} from './interfaces/AssistantApplicationPort';
import type { VoiceTransportConnection } from './interfaces/VoiceTransportPort';

const AUDIO_FORMAT = 'pcm_s16le';
const SAMPLE_RATE_HZ = 16000;
const CHANNELS = 1;
// 服务端握手超时默认 5s（TIMEFLOW_WS_HANDSHAKE_TIMEOUT_SECONDS）；定位留出一部分
// 预算，超时就不带，不能让 hello 本身也赶不上。
const LOCATION_TIMEOUT_MS = 2000;

/**
 * 免提连续对话编排：一次 startTurn() 打开麦克风、发一次 voice.stream.start，
 * 之后持续推流直到 endTurn() 主动关闭。一次开麦期间服务端可能触发多轮
 * transcript/回复（由 vendor 的 turn_detection 决定边界），所以这里完成一轮
 * 后回到 'listening' 而不是 'idle'，且新增了处理 voice.tts.canceled（被打断）
 * 的分支。
 *
 * 与 AssistantConversationService（按住说话）刻意保持两个独立的类，不共享
 * connect() 实现：这批端口本身够通用，但两条编排路径的状态机形状不同，合并
 * 会让按住说话那条已经在用的路径承担连续模式的改动风险。
 */
export class AssistantContinuousConversationService implements AssistantApplicationPort {
  private connection: VoiceTransportConnection | null = null;
  private state: ConversationTurnState = { phase: 'idle' };
  private lastAppliedCommand: AppliedCommand | null = null;
  private readonly listeners = new Set<(state: ConversationTurnState) => void>();

  private conversationId: string | null = null;
  private streamId: string | null = null;
  /** 非 null 表示当前正处于 voice.tts.start 和 voice.tts.end/canceled 之间。 */
  private currentAudioId: string | null = null;
  private streamStartedWaiter: ((conversationId: string) => void) | null = null;
  private replyText: string | null = null;
  private soundLevel: number | null = null;

  constructor(
    private readonly options: AssistantApplicationOptions,
    private readonly deps: AssistantApplicationDependencies,
  ) {}

  getState(): ConversationTurnState {
    return this.state;
  }

  subscribe(listener: (state: ConversationTurnState) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  getLastAppliedCommand(): AppliedCommand | null {
    return this.lastAppliedCommand;
  }

  getReplyText(): string | null {
    return this.replyText;
  }

  getSoundLevel(): number | null {
    return this.soundLevel;
  }

  /** 打开连续会话：建连、开一次流、开始持续推流麦克风。 */
  async startTurn(): Promise<void> {
    this.replyText = null;
    this.soundLevel = null;
    this.setState({ phase: 'connecting' });
    await this.connect();
    const connection = this.requireConnection();

    const started = new Promise<string>((resolve) => {
      this.streamStartedWaiter = resolve;
    });
    connection.send({
      payload: {
        audio_format: AUDIO_FORMAT,
        channels: CHANNELS,
        conversation_id: this.conversationId ?? undefined,
        sample_rate_hz: SAMPLE_RATE_HZ,
      },
      type: 'voice.stream.start',
    });
    const conversationId = await started;

    await this.deps.capture.requestPermission();
    await this.deps.capture.start((chunk, soundLevel) => {
      connection.sendAudioFrame(chunk);
      this.soundLevel = soundLevel;
      this.notifyListeners();
    });
    this.setState({ conversationId, phase: 'listening' });
  }

  /** 关闭连续会话：关麦、结束流、断开连接。 */
  async endTurn(): Promise<void> {
    await this.deps.capture.stop();
    this.soundLevel = null;
    const connection = this.connection;
    if (connection !== null && this.streamId !== null) {
      connection.send({
        payload: { stream_id: this.streamId },
        type: 'voice.stream.end',
      });
      this.streamId = null;
    }
    connection?.close();
    this.connection = null;
    this.setState({ phase: 'idle' });
  }

  async dismissReply(): Promise<void> {
    this.replyText = null;
    this.currentAudioId = null;
    this.notifyListeners();
    await this.deps.playback.stop().catch(() => {});
  }

  dispose(): void {
    this.listeners.clear();
    // 连续模式麦克风开着的时间远长于按住说话的一次按住，组件卸载时更可能还在
    // 录，兜底停一下——失败也不影响清理连接。
    void this.deps.capture.stop().catch(() => {});
    this.connection?.close();
    this.connection = null;
  }

  private async connect(): Promise<void> {
    // 定位放在开连接之前:服务端握手超时从 socket 打开那一刻起计时,原生定位
    // (尤其冷启动 GPS)可能耗时数秒,放在连接之后拿会把这段时间算进握手预算,
    // 导致 hello 送达前就被服务端以 1008 断开。超时兜底,拿不到就不带,不阻塞握手。
    const sample = await Promise.race([
      this.deps.location.getCurrentSample().catch(() => null),
      new Promise<null>((resolve) => setTimeout(() => resolve(null), LOCATION_TIMEOUT_MS)),
    ]);

    const connection = await this.deps.transport.connect(this.options.wsUrl);
    this.connection = connection;
    connection.onMessage((message) => this.handleMessage(message));
    connection.onAudioFrame((chunk) => this.handleAudioFrame(chunk));
    connection.onClose((event) => this.handleClose(event));

    const ready = new Promise<void>((resolve) => {
      const unsubscribe = connection.onMessage((message) => {
        if (message.type === 'session.ready') {
          unsubscribe();
          resolve();
        }
      });
    });
    connection.send({
      payload: {
        access_token: this.options.accessToken,
        device_id: this.options.deviceId,
        latitude: sample?.latitude,
        longitude: sample?.longitude,
        voice_mode: 'continuous',
      },
      type: 'session.hello',
    });
    await ready;
  }

  private handleMessage(message: AssistantServerMessage): void {
    if (isTransportError(message)) {
      this.setState({ message: message.error.message, phase: 'error' });
      return;
    }

    switch (message.type) {
      case 'voice.stream.started':
        this.streamId = message.payload.stream_id;
        this.conversationId = message.payload.conversation_id;
        this.streamStartedWaiter?.(message.payload.conversation_id);
        this.streamStartedWaiter = null;
        return;
      case 'voice.command.result': {
        const command: AppliedCommand = {
          operation: message.payload.operation,
          schedule: message.payload.schedule,
          schedules: message.payload.schedules,
          status: message.payload.status,
        };
        // 写本地库是异步的，不等它：ack 和状态回 listening 立刻做，避免这轮对话
        // 因为一次 SQLite 写入卡住。lastAppliedCommand 在写库落定后才更新。
        void this.applyCommandResultLocally(command);
        if (this.connection !== null) {
          this.connection.send({
            message_id: message.message_id,
            status: 'applied',
            type: 'message.ack',
          });
        }
        // 麦克风还开着，回 listening 而不是掉回空闲态。
        this.setState({ conversationId: message.conversation_id, phase: 'listening' });
        return;
      }
      case 'voice.dialogue.question':
        this.setState({
          conversationId: message.conversation_id,
          phase: 'asking',
          speechText: message.payload.speech_text,
        });
        return;
      case 'voice.dialogue.reply':
        this.replyText = message.payload.speech_text;
        this.notifyListeners();
        return;
      case 'voice.tts.start':
        this.currentAudioId = message.audio_id;
        this.setState({ conversationId: message.conversation_id, phase: 'speaking' });
        this.deps.playback
          .startStream({
            encoding: 'pcm_s16le',
            sampleRateHz: message.payload.sample_rate_hz,
          })
          .catch(() => {});
        return;
      case 'voice.tts.end':
        this.currentAudioId = null;
        this.deps.playback.endStream().catch(() => {});
        this.setState({ conversationId: message.conversation_id, phase: 'listening' });
        return;
      case 'voice.tts.canceled':
        // 用户开口打断了正在播的回复：立刻丢掉播放端缓冲里还没放出来的音频，
        // 而不是等 voice.tts.end（后面仍会补发，但语义已经不是"正常说完"）。
        this.currentAudioId = null;
        void this.deps.playback.stop().catch(() => {});
        this.setState({ conversationId: message.conversation_id, phase: 'interrupted' });
        return;
      default:
        return;
    }
  }

  private async applyCommandResultLocally(command: AppliedCommand): Promise<void> {
    try {
      await this.deps.localScheduleWriter.applyCommandResult(this.options.accountId, command);
    } catch {
      // 写本地失败不影响这轮对话已经完成；不重试，下次操作会带着新数据重新覆盖。
    }
    this.lastAppliedCommand = command;
    this.notifyListeners();
  }

  private handleAudioFrame(chunk: ArrayBuffer): void {
    if (this.currentAudioId === null) {
      return;
    }
    this.deps.playback.pushChunk(chunk).catch(() => {});
  }

  private handleClose(event: { code: number; reason: string }): void {
    this.connection = null;
    this.setState({ message: event.reason || `连接已断开（${event.code}）`, phase: 'error' });
  }

  private requireConnection(): VoiceTransportConnection {
    if (this.connection === null) {
      throw new Error('startTurn called without an open connection');
    }
    return this.connection;
  }

  private setState(state: ConversationTurnState): void {
    this.state = state;
    this.notifyListeners();
  }

  private notifyListeners(): void {
    for (const listener of this.listeners) {
      listener(this.state);
    }
  }
}
