import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import { Platform } from 'react-native';
import { getOrCreateDeviceId } from './device';
import { registerDevice } from './api';

const USE_FCM = false; // TODO: set to true when testing an EAS development build with Firebase

/**
 * Note: Expo Go notification work is local-only for development testing.
 * Real backend-triggered emergency push requires either:
 *  - EAS development build + Firebase FCM token registration, or
 *  - Backend support for Expo push service.
 */

export async function setupNotifications() {
  try {
    if (Platform.OS === 'android') {
      await Notifications.setNotificationChannelAsync('urgent_alerts', {
        name: 'urgent_alerts',
        importance: Notifications.AndroidImportance.HIGH,
        vibrationPattern: [0, 250, 250, 250],
        lightColor: '#10b981',
      });
    }

    const { status: existingStatus } = await Notifications.getPermissionsAsync();
    let finalStatus = existingStatus;
    if (existingStatus !== 'granted') {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }

    if (finalStatus !== 'granted') {
      console.warn('Notification permission not granted');
      return;
    }

    // Skip token acquisition on simulators/emulators
    if (!Device.isDevice) {
      console.log('Not a physical device; skipping push token acquisition.');
      return;
    }

    let tokenData;
    let provider;
    if (USE_FCM) {
      tokenData = await Notifications.getDevicePushTokenAsync();
      provider = 'fcm';
    } else {
      tokenData = await Notifications.getExpoPushTokenAsync();
      provider = 'expo';
    }

    const pushToken = tokenData?.data;

    if (!pushToken) {
      console.warn('Push token acquisition returned empty; skipping device registration.');
      return;
    }

    const deviceId = await getOrCreateDeviceId();

    await registerDevice({
      device_id: deviceId,
      platform: 'android',
      push_provider: provider,
      push_token: pushToken,
      role: 'patient',
    });

    console.log('Device registered for push notifications:', pushToken);
  } catch (e) {
    console.warn('Notification setup failed:', e.message);
  }
}

export async function scheduleGeofenceNotification({ alert_id, title, body, delaySeconds = 8 } = {}) {
  try {
    await Notifications.scheduleNotificationAsync({
      content: {
        title: title || 'Memoria location check',
        body: body || 'I noticed you are far from home. Is everything ok?',
        data: {
          url: `memoria://alerts/${alert_id}`,
          alert_id,
        },
      },
      trigger: { seconds: Math.max(1, Math.floor(delaySeconds)) },
    });
    console.log('Geofence notification scheduled for alert:', alert_id);
  } catch (e) {
    console.error('Failed to schedule geofence notification:', e);
  }
}

export async function sendTestNotification() {
  try {
    await Notifications.scheduleNotificationAsync({
      content: {
        title: 'Test Alert',
        body: 'Tap to open alert detail',
        data: {
          url: 'memoria://alerts/test-id',
          alert_id: 'test-id',
        },
      },
      trigger: null, // immediate
    });
    console.log('Test notification scheduled');
  } catch (e) {
    console.error('Failed to schedule test notification:', e);
  }
}
