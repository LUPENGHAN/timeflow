/**
 * 一轮语音交互的状态机。纯类型，不依赖 React/WS/录音 SDK，方便展示层和应用层
 * 各自按需渲染或编排，而不必读懂传输细节。
 */

export type ConversationTurnState =
  | { phase: 'idle' }
  | { phase: 'connecting' }
  | { phase: 'recording'; conversationId: string | null }
  | { phase: 'awaiting_result'; conversationId: string }
  | { phase: 'asking'; conversationId: string; speechText: string }
  | { phase: 'speaking'; conversationId: string }
  /** 连续模式专属：麦克风开着、待命中，既没在说话也没在播放回复。 */
  | { phase: 'listening'; conversationId: string | null }
  /** 连续模式专属：刚收到 voice.tts.canceled，用户的话打断了正在播的回复。 */
  | { phase: 'interrupted'; conversationId: string }
  | { phase: 'error'; message: string };

export interface AppliedCommand {
  operation: string;
  status: string;
  schedule?: Record<string, unknown>;
  schedules?: Record<string, unknown>[];
}
