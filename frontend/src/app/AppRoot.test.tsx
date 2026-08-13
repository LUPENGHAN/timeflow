import { beforeEach, describe, expect, it, jest } from '@jest/globals';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

import { accessAuth } from '../api/auth';
import type { AuthAccessResponse } from '../contracts/auth';
import { AppRoot } from './AppRoot';

jest.mock('../api/auth', () => ({
  accessAuth: jest.fn(),
}));

jest.mock('../infrastructure/database', () => ({
  openTimeflowDatabase: jest.fn<() => Promise<unknown>>().mockResolvedValue({}),
}));
jest.mock('../features/schedule/data', () => ({ ScheduleLocalRepository: jest.fn() }));
jest.mock('../features/schedule/application', () => ({ SqliteScheduleClientService: jest.fn() }));
// 日历屏本身有自己的测试（ScheduleCalendarScreen.test.tsx），这里只需要确认
// 登录 + 本地库初始化之后能进到日历这条路径，不需要日历内部的真实渲染。
jest.mock('../features/schedule/presentation/ScheduleCalendarScreen', () => ({
  ScheduleCalendarScreen: () => {
    const { Text: NativeText } = jest.requireActual(
      'react-native',
    ) as typeof import('react-native');
    return <NativeText>日程日历</NativeText>;
  },
}));

// 定位/录音播放都是原生模块，jest 环境里没有对应的原生实现，这里只验证登录后
// 能渲染出主屏，不需要它们真的工作。
jest.mock('expo-location', () => ({
  getCurrentPositionAsync: jest.fn(),
  requestForegroundPermissionsAsync: jest.fn(),
}));

jest.mock('@irvingouj/expo-audio-stream', () => ({
  EncodingTypes: { PCM_F32LE: 'pcm_f32le', PCM_S16LE: 'pcm_s16le' },
  ExpoPlayAudioStream: {
    playAudio: jest.fn(),
    setSoundConfig: jest.fn(),
    startMicrophone: jest.fn(),
    stopMicrophone: jest.fn(),
  },
}));

const mockedAccessAuth = accessAuth as jest.MockedFunction<typeof accessAuth>;
const tokenResponse: AuthAccessResponse = {
  account_id: 'acc_001',
  access_token: 'access-token',
  expires_in: 3600,
};

beforeEach(() => {
  mockedAccessAuth.mockReset();
});

describe('AppRoot', () => {
  it('enters the calendar after authentication without exposing the token', async () => {
    mockedAccessAuth.mockResolvedValue(tokenResponse);
    render(<AppRoot />);

    fireEvent.changeText(screen.getByLabelText('用户名'), 'timeflow_user');
    fireEvent.changeText(screen.getByLabelText('密码'), 'password123');
    fireEvent.press(screen.getByRole('button', { name: '继续' }));

    await waitFor(() => {
      expect(screen.getByText('日程日历')).toBeTruthy();
    });
    expect(screen.queryByText('登录或注册')).toBeNull();
    expect(screen.queryByText('access-token')).toBeNull();
  });

  it('can retry local database initialization after a failure', async () => {
    const { openTimeflowDatabase } = jest.requireMock('../infrastructure/database') as {
      openTimeflowDatabase: jest.MockedFunction<() => Promise<unknown>>;
    };
    openTimeflowDatabase.mockReset();
    openTimeflowDatabase
      .mockRejectedValueOnce(new Error('database unavailable'))
      .mockResolvedValue({});
    mockedAccessAuth.mockResolvedValue(tokenResponse);
    render(<AppRoot />);

    fireEvent.changeText(screen.getByLabelText('用户名'), 'timeflow_user');
    fireEvent.changeText(screen.getByLabelText('密码'), 'password123');
    fireEvent.press(screen.getByRole('button', { name: '继续' }));

    await waitFor(() => expect(screen.getByText('本地日程存储初始化失败')).toBeTruthy());
    fireEvent.press(screen.getByText('重试'));
    await waitFor(() => expect(screen.getByText('日程日历')).toBeTruthy());
    expect(openTimeflowDatabase).toHaveBeenCalledTimes(2);
  });
});
