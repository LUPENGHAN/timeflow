const { AndroidConfig, createRunOncePlugin, withAndroidManifest } = require('expo/config-plugins');

const PACKAGE_NAME = 'timeflow-alarm';
const PERMISSIONS = [
  'android.permission.POST_NOTIFICATIONS',
  'android.permission.SCHEDULE_EXACT_ALARM',
  'android.permission.SYSTEM_ALERT_WINDOW',
  'android.permission.USE_FULL_SCREEN_INTENT',
  'android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS',
  'android.permission.VIBRATE',
  'android.permission.FOREGROUND_SERVICE',
  'android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK',
];

/**
 * Android 11+（targetSdk 30+）的包可见性限制会让 TextToSpeech 内部查询"设备上有
 * 哪些 TTS 引擎"时直接查到空列表——即使系统设置里试听正常、引擎确实装着，
 * 也会导致 new TextToSpeech(...) 的初始化回调稳定收到 status=ERROR（真机 adb
 * logcat 实测过：连"App 前台手动探测"这条路径都失败，排除了后台限制的可能，
 * 定位到就是这条包可见性规则）。这里声明的 intent action 是 Android 官方文档
 * 明确点名要求声明的那个：
 * https://developer.android.com/reference/android/speech/tts/TextToSpeech.Engine#INTENT_ACTION_TTS_SERVICE
 */
const TTS_SERVICE_ACTION = 'android.speech.tts.TextToSpeech.Engine.INTENT_ACTION_TTS_SERVICE';

function withTtsEngineVisibility(config) {
  return withAndroidManifest(config, (config) => {
    const manifest = config.modResults.manifest;
    manifest.queries = manifest.queries ?? [];
    const alreadyDeclared = manifest.queries.some((query) =>
      (query.intent ?? []).some((intent) =>
        (intent.action ?? []).some((action) => action.$['android:name'] === TTS_SERVICE_ACTION),
      ),
    );
    if (!alreadyDeclared) {
      manifest.queries.push({
        intent: [{ action: [{ $: { 'android:name': TTS_SERVICE_ACTION } }] }],
      });
    }
    return config;
  });
}

/**
 * 保证应用级闹钟权限在 prebuild 后仍然保留。
 * 原生源码、AlarmPackage 自动链接与组件声明在 modules/timeflow-alarm
 * （经 Android library manifest 合并）。
 */
function withTimeflowAlarm(config) {
  config = AndroidConfig.Permissions.withPermissions(config, PERMISSIONS);
  config = withAndroidManifest(config, (config) => {
    AndroidConfig.Permissions.ensurePermissions(config.modResults, PERMISSIONS);
    return config;
  });
  config = withTtsEngineVisibility(config);
  return config;
}

module.exports = createRunOncePlugin(withTimeflowAlarm, PACKAGE_NAME, '1.0.0');
