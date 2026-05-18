import AsyncStorage from '@react-native-async-storage/async-storage';

const SESSION_KEY = 'memoria_conversation_session_id';

function generateSessionId() {
  // Simple UUID v4 generator
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export async function getOrCreateSessionId() {
  try {
    const existing = await AsyncStorage.getItem(SESSION_KEY);
    if (existing) return existing;
    const next = generateSessionId();
    await AsyncStorage.setItem(SESSION_KEY, next);
    return next;
  } catch (e) {
    console.error('Session storage error:', e);
    return generateSessionId();
  }
}

export async function resetSessionId() {
  try {
    const next = generateSessionId();
    await AsyncStorage.setItem(SESSION_KEY, next);
    return next;
  } catch (e) {
    console.error('Session reset error:', e);
    return generateSessionId();
  }
}
