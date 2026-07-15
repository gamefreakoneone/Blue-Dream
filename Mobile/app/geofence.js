import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Linking,
  ActivityIndicator,
  ScrollView,
} from 'react-native';
import * as Notifications from 'expo-notifications';
import { COLORS } from '../constants/theme';
import { getGeofence, recordGeofenceEvent } from '../lib/api';
import { getOrCreateDeviceId } from '../lib/device';

export default function GeofenceScreen() {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [arming, setArming] = useState(false);
  const countdownRef = useRef(null);

  useEffect(() => {
    let mounted = true;
    getGeofence()
      .then((data) => {
        if (mounted) setConfig(data);
      })
      .catch((e) => {
        if (mounted) setError(e.message);
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  // Clean up any pending countdown on unmount
  useEffect(() => {
    return () => {
      if (countdownRef.current) {
        clearTimeout(countdownRef.current);
      }
    };
  }, []);

  const getHomeCoords = () => {
    const lat = config?.home_lat;
    const lng = config?.home_lng;
    if (Number.isFinite(lat) && Number.isFinite(lng)) {
      return { lat, lng };
    }
    return null;
  };

  const openMapsNavigation = (lat, lng) => {
    if (typeof lat !== 'number' || typeof lng !== 'number') return;
    const url = `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`;
    Linking.openURL(url).catch((e) => {
      console.error('Failed to open maps:', e);
    });
  };

  const handleGuideMeHome = () => {
    const homeCoords = getHomeCoords();
    if (!homeCoords) {
      setError('Home coordinates are not configured.');
      return;
    }
    const { lat, lng } = homeCoords;
    openMapsNavigation(lat, lng);
  };

  const handleLongPress = () => {
    if (!getHomeCoords()) {
      setError('Home coordinates are not configured.');
      return;
    }
    // Start invisible countdown: create backend alert + schedule notification after delay
    setArming(true);
    countdownRef.current = setTimeout(() => {
      triggerGeofenceExitDemo();
    }, 1200); // 1.2s to allow deliberate long-press but fast enough
  };

  const handlePressOut = () => {
    if (countdownRef.current) {
      clearTimeout(countdownRef.current);
      countdownRef.current = null;
    }
    setArming(false);
  };

  const triggerGeofenceExitDemo = async () => {
    try {
      const homeCoords = getHomeCoords();
      if (!homeCoords) {
        throw new Error('Home coordinates are not configured.');
      }
      const radiusMeters = Number(config?.radius_meters) || 100;
      const latitudeOffset = Math.max((radiusMeters * 1.5) / 111320, 0.001);
      const deviceId = await getOrCreateDeviceId();
      // Report a location beyond the configured radius so it appears as an exit.
      const alert = await recordGeofenceEvent({
        event_type: 'exit',
        latitude: homeCoords.lat + latitudeOffset,
        longitude: homeCoords.lng,
        device_id: deviceId,
      });

      // Schedule local notification 8 seconds later so the user can lock the phone
      await Notifications.scheduleNotificationAsync({
        content: {
          title: alert.title || 'Memoria location check',
          body: alert.body || 'I noticed you are far from home. Is everything ok?',
          data: {
            url: `memoria://alerts/${alert.alert_id}`,
            alert_id: alert.alert_id,
          },
        },
        trigger: { seconds: 8 },
      });

      console.log('Geofence demo armed. Notification will fire in ~8 seconds.');
    } catch (e) {
      setError(e.message);
      console.error('Geofence demo trigger failed:', e.message);
    } finally {
      setArming(false);
    }
  };

  const homeCoords = getHomeCoords();

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {loading && (
        <ActivityIndicator size="large" color={COLORS.primary} />
      )}

      {!loading && error && (
        <Text style={styles.errorText}>{error}</Text>
      )}

      {!loading && (
        <>
          <Text style={styles.title}>Geofence</Text>
          <Text style={styles.body}>
            {homeCoords ? (
              <>
                Home is set at{' '}
                <Text style={styles.coord}>
                  {homeCoords.lat.toFixed(5)}, {homeCoords.lng.toFixed(5)}
                </Text>
              </>
            ) : (
              <Text style={styles.errorText}>Home coordinates are not configured.</Text>
            )}
            {'\n\n'}
            If you ever need help finding your way back, tap below.
          </Text>

          <TouchableOpacity
            style={[
              styles.btn,
              arming && styles.btnArming,
              !homeCoords && styles.btnDisabled,
            ]}
            onPress={handleGuideMeHome}
            onLongPress={handleLongPress}
            onPressOut={handlePressOut}
            delayLongPress={1200}
            activeOpacity={0.8}
            disabled={!homeCoords}
          >
            <Text style={styles.btnText}>Guide me home</Text>
          </TouchableOpacity>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.bg,
  },
  content: {
    padding: 28,
    alignItems: 'center',
    justifyContent: 'center',
    flexGrow: 1,
  },
  title: {
    fontSize: 22,
    fontWeight: '700',
    color: COLORS.text,
    marginBottom: 14,
    textAlign: 'center',
  },
  body: {
    fontSize: 15,
    color: COLORS.secondaryText,
    textAlign: 'center',
    lineHeight: 23,
    marginBottom: 24,
  },
  coord: {
    fontWeight: '600',
    color: COLORS.text,
  },
  errorText: {
    fontSize: 14,
    color: '#ef4444',
    textAlign: 'center',
  },
  btn: {
    backgroundColor: COLORS.primary,
    paddingVertical: 16,
    paddingHorizontal: 36,
    borderRadius: 14,
    marginBottom: 24,
  },
  btnArming: {
    backgroundColor: '#059669',
  },
  btnDisabled: {
    backgroundColor: '#64748b',
    opacity: 0.6,
  },
  btnText: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '600',
  },
});
