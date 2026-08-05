import type { CommonPowerSyncDatabase, QueryResult } from '@powersync/common';

import type {
  Schedule,
  ScheduleDeletedAck,
  ScheduleListQueryPayload,
  ScheduleStatus,
  ScheduleStatusUpdateResponse,
  ScheduleUpsertCommand,
  ScheduleUpsertResponse,
} from '@/contracts';
import {
  WsScheduleRepository,
  type SchedulePushEvent,
  type ScheduleRepositoryPort,
  type ScheduleTransport,
} from '@/features/schedule';

type PowerSyncScheduleRow = Omit<Schedule, 'geofence_armed'> & {
  geofence_armed: number | bigint | boolean;
};

type ScheduleQuery = {
  sql: string;
  parameters: (string | boolean)[];
};

function toSchedule(row: PowerSyncScheduleRow): Schedule {
  return {
    ...row,
    geofence_armed: Number(row.geofence_armed) === 1,
  };
}

function buildScheduleQuery(userId: string, query: ScheduleListQueryPayload): ScheduleQuery {
  const conditions = ['user_id = ?'];
  const parameters: (string | boolean)[] = [userId];

  if (query.status !== null) {
    conditions.push('status = ?');
    parameters.push(query.status);
  } else if (!query.include_deleted) {
    conditions.push("status != 'deleted'");
  }

  return {
    sql: `SELECT * FROM schedules WHERE ${conditions.join(' AND ')}`,
    parameters,
  };
}

/** Reads server-authoritative schedules from PowerSync while writes remain on WebSocket. */
export class PowerSyncScheduleRepository implements ScheduleRepositoryPort {
  private readonly writeRepository: WsScheduleRepository;
  private readonly listeners = new Set<(event: SchedulePushEvent) => void>();
  private watchAbortController: AbortController | null = null;
  private activeQuery: ScheduleListQueryPayload = {
    status: null,
    include_deleted: false,
  };

  constructor(
    private readonly database: CommonPowerSyncDatabase,
    transport: ScheduleTransport,
    private readonly userId: string,
  ) {
    this.writeRepository = new WsScheduleRepository(transport);
  }

  async list(query: ScheduleListQueryPayload): Promise<Schedule[]> {
    this.activeQuery = query;
    const statement = buildScheduleQuery(this.userId, query);
    const rows = await this.database.getAll<PowerSyncScheduleRow>(
      statement.sql,
      statement.parameters,
    );
    return rows.map(toSchedule);
  }

  upsert(command: ScheduleUpsertCommand): Promise<ScheduleUpsertResponse> {
    return this.writeRepository.upsert(command);
  }

  updateStatus(
    scheduleId: string,
    status: Extract<ScheduleStatus, 'scheduled' | 'done'>,
  ): Promise<ScheduleStatusUpdateResponse> {
    return this.writeRepository.updateStatus(scheduleId, status);
  }

  notifyDeleted(scheduleId: string): Promise<ScheduleDeletedAck> {
    return this.writeRepository.notifyDeleted(scheduleId);
  }

  subscribe(listener: (event: SchedulePushEvent) => void): () => void {
    this.listeners.add(listener);
    if (!this.watchAbortController) this.startWatch();

    return () => {
      this.listeners.delete(listener);
      if (this.listeners.size === 0) this.stopWatch();
    };
  }

  dispose(): void {
    this.stopWatch();
    this.listeners.clear();
    this.writeRepository.dispose();
  }

  private startWatch(): void {
    const abortController = new AbortController();
    this.watchAbortController = abortController;
    const statement = buildScheduleQuery(this.userId, this.activeQuery);
    this.database.watch(
      statement.sql,
      statement.parameters,
      {
        onResult: (result: QueryResult) => {
          const schedules = (result.array as unknown as PowerSyncScheduleRow[]).map(toSchedule);
          for (const listener of this.listeners) {
            listener({ type: 'schedule.snapshot', schedules });
          }
        },
        onError: (error) => {
          console.warn('[PowerSync] schedule query failed', error);
        },
      },
      { signal: abortController.signal, triggerImmediate: true },
    );
  }

  private stopWatch(): void {
    this.watchAbortController?.abort();
    this.watchAbortController = null;
  }
}
