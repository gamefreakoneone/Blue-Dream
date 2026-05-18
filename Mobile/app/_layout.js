import React, { createContext, useEffect, useRef } from 'react';
import { View, Text, Image, TouchableOpacity, StyleSheet, Linking } from 'react-native';
import { Stack, useRouter } from 'expo-router';
import * as Notifications from 'expo-notifications';
import { COLORS } from '../constants/theme';
import { setupNotifications } from '../lib/notifications';

export const NewChatContext = createContext({ trigger: () => {} });

function HeaderLeft() {
  return (
    <View style={styles.headerLeft}>
      <Image source={require('../assets/slime_logo.png')} style={styles.logo} />
      <Text style={styles.title}>Memoria</Text>
    </View>
  );
}

function HeaderRight() {
  const router = useRouter();
  const signalRef = useRef(null);
  try {
    // Access the nearest provider value if available
    const ctx = React.useContext(NewChatContext);
    signalRef.current = ctx;
  } catch {
    // noop
  }

  return (
    <View style={styles.headerRight}>
      <TouchableOpacity
        onPress={() => signalRef.current?.trigger?.()}
        style={styles.iconBtn}
        activeOpacity={0.7}
      >
        <Text style={styles.iconText}>＋</Text>
      </TouchableOpacity>
      <TouchableOpacity
        onPress={() => router.push('/alerts')}
        style={styles.iconBtn}
        activeOpacity={0.7}
      >
        <Text style={styles.iconText}>🔔</Text>
      </TouchableOpacity>
    </View>
  );
}

export default function RootLayout() {
  const signalRef = useRef({ callback: null });
  const router = useRouter();

  const trigger = () => {
    if (typeof signalRef.current.callback === 'function') {
      signalRef.current.callback();
    }
  };

  // Initialize notifications on app launch
  useEffect(() => {
    setupNotifications();
  }, []);

  // Handle notification response (user taps a notification)
  useEffect(() => {
    const subscription = Notifications.addNotificationResponseReceivedListener((response) => {
      const data = response?.notification?.request?.content?.data || {};

      // Support both data.url and data.alert_id for routing
      let alertId = null;
      if (data.url && typeof data.url === 'string') {
        const match = data.url.match(/^memoria:\/\/alerts\/(.+)$/);
        if (match) alertId = match[1];
      }
      if (!alertId && data.alert_id) {
        alertId = data.alert_id;
      }

      if (alertId) {
        router.push(`/alerts/${alertId}`);
      }
    });

    return () => subscription.remove();
  }, [router]);

  // Handle cold-start deep links
  useEffect(() => {
    let mounted = true;
    Linking.getInitialURL().then((url) => {
      if (!mounted || !url) return;
      const match = url.match(/^memoria:\/\/alerts\/(.+)$/);
      if (match) {
        router.push(`/alerts/${match[1]}`);
      }
    });
    return () => {
      mounted = false;
    };
  }, [router]);

  return (
    <NewChatContext.Provider value={{ trigger, ref: signalRef }}>
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: COLORS.chatBg },
          headerShadowVisible: false,
          contentStyle: { backgroundColor: COLORS.bg },
        }}
      >
        <Stack.Screen
          name="index"
          options={{
            headerTitle: () => <HeaderLeft />,
            headerTitleAlign: 'left',
            headerRight: () => <HeaderRight />,
          }}
        />
        <Stack.Screen
          name="alerts/index"
          options={{ title: 'Alerts', headerBackTitle: 'Back' }}
        />
        <Stack.Screen
          name="alerts/[id]"
          options={{ title: 'Alert Detail', headerBackTitle: 'Back' }}
        />
        <Stack.Screen
          name="geofence"
          options={{ title: 'Geofence', headerBackTitle: 'Back' }}
        />
      </Stack>
    </NewChatContext.Provider>
  );
}

const styles = StyleSheet.create({
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  logo: {
    width: 32,
    height: 32,
    resizeMode: 'contain',
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
    color: COLORS.primary,
    letterSpacing: -0.5,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  iconBtn: {
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  iconText: {
    fontSize: 20,
  },
});
