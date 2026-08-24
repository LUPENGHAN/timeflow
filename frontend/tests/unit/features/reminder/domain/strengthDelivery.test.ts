import { describe, expect, it } from '@jest/globals';

import type {
  LocalReminderSchedule,
  ReminderStrength,
} from '../../../../../src/features/reminder/domain';
import {
  composeReminderSpeech,
  resolveStrengthDeliveryPlan,
} from '../../../../../src/features/reminder/domain/strengthDelivery';

describe('resolveStrengthDeliveryPlan', () => {
  it('low: system notification only, native ring page gets a one-shot ping', () => {
    expect(resolveStrengthDeliveryPlan('low')).toEqual({
      useSystemNotification: true,
      usePopup: false,
      useVibration: false,
      useAudio: false,
      alarmSoundTier: 'ping',
    });
  });

  it('medium: popup + vibration, no JS audio, native ring page gets a one-shot ping', () => {
    expect(resolveStrengthDeliveryPlan('medium')).toEqual({
      useSystemNotification: false,
      usePopup: true,
      useVibration: true,
      useAudio: false,
      alarmSoundTier: 'ping',
    });
  });

  it('high: popup + vibration + audio, native ring page gets the full looping sound', () => {
    expect(resolveStrengthDeliveryPlan('high')).toEqual({
      useSystemNotification: false,
      usePopup: true,
      useVibration: true,
      useAudio: true,
      alarmSoundTier: 'full',
    });
  });
});

describe('composeReminderSpeech', () => {
  it('high with title only wraps it with a reminder prefix and suffix', () => {
    expect(composeReminderSpeech(speechSchedule('high', ' 九点面试 ', null))).toBe(
      '提醒你，九点面试，别忘了',
    );
  });

  it('high with location appends the location before the suffix', () => {
    expect(composeReminderSpeech(speechSchedule('high', '拿快递', '家'))).toBe(
      '提醒你，拿快递，地点在家，别忘了',
    );
  });

  it('high with blank location falls back to title only', () => {
    expect(composeReminderSpeech(speechSchedule('high', '开会', '  '))).toBe(
      '提醒你，开会，别忘了',
    );
  });

  it('non-high returns empty string', () => {
    expect(composeReminderSpeech(speechSchedule('medium', '开会', '家'))).toBe('');
    expect(composeReminderSpeech(speechSchedule('low', '开会', '家'))).toBe('');
  });

  it('high with blank title returns empty string', () => {
    expect(composeReminderSpeech(speechSchedule('high', '   ', '家'))).toBe('');
  });
});

function speechSchedule(
  strength: ReminderStrength,
  title: string,
  locationName: string | null,
): LocalReminderSchedule {
  return {
    id: 's1',
    account_id: 'acc',
    title,
    schedule_type: 'time',
    schedule_kind: 'once',
    is_all_day: false,
    start_time: '2026-08-18T10:00:00.000Z',
    end_time: null,
    timezone: 'Asia/Shanghai',
    recurrence_rule: null,
    location_name: locationName,
    latitude: null,
    longitude: null,
    geofence_radius_meters: 200,
    reminder: {
      reminder_type: 'at_time',
      reminder_trigger_at: null,
      reminder_offset_minutes: null,
      reminder_strength: strength,
    },
    runtime: {
      reminder_disposition_state: null,
      next_trigger_at: null,
      snoozed_until: null,
      geofence_armed: false,
      disposition_updated_at: null,
      sync_status: 'pending',
      recorded_location: null,
    },
    status: 'active',
    revision: 1,
    cloud_revision: 1,
    updated_at: '2026-08-18T09:00:00.000Z',
  };
}
