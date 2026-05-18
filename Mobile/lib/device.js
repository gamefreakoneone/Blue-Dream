import AsyncStorage from '@react-native-async-storage/async-storage';

const DEVICE_ID_KEY = 'memoria_device_id';

function generateDeviceId() {
  // Simple UUID v4 generator
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export async function getOrCreateDeviceId() {
  try {
    const existing = await AsyncStorage.getItem(DEVICE_ID_KEY);
    if (existing) return existing;
    const next = generateDeviceId();
    await AsyncStorage.setItem(DEVICE_ID_KEY, next);
    return next;
  } catch (e) {
    console.error('Device ID storage error:', e);
    return generateDeviceId();
  }
}
