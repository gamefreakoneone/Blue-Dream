import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Linking,
  ActivityIndicator,
  ScrollView,
} from 'react-native';
import { COLORS } from '../constants/theme';
import { getGeofence } from '../lib/api';
import { sendTestNotification } from '../lib/notifications';

const FALLBACK_LAT = 34.034992564747604;
const FALLBACK_LNG = -118.28252676933066;

export default function GeofenceScreen() {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

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

  const getHomeCoords = () => {
    const lat = config?.home_lat;
    const lng = config?.home_lng;
    if (typeof lat === 'number' && typeof lng === 'number') {
      return { lat, lng, source: 'backend' };
    }
    return { lat: FALLBACK_LAT, lng: FALLBACK_LNG, source: 'fallback' };
  };

  const openMapsNavigation = () => {
    const { lat, lng } = getHomeCoords();
    if (typeof lat !== 'number' || typeof lng !== 'number') return;
    const url = `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`;
    Linking.openURL(url).catch((e) => {
      console.error('Failed to open maps:', e);
    });
  };

  const { lat, lng, source } = getHomeCoords();

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {loading && (
        <ActivityIndicator size="large" color={COLORS.primary} />
      )}

      {!loading && error && (
        <Text style={styles.errorText}>Could not load geofence: {error}</Text>
      )}

      {!loading && (
        <>
          <Text style={styles.title}>Geofence</Text>
          <Text style={styles.body}>
            Home is set at{' '}
            <Text style={styles.coord}>
              {lat.toFixed(5)}, {lng.toFixed(5)}
            </Text>
            {source === 'fallback' && (
              <Text style={styles.fallbackNote}>
                {'\n\n'}(Using fallback coordinates because backend geofence is not configured.)
              </Text>
            )}
            {'\n\n'}
            If you ever need help finding your way back, tap below.
          </Text>

          <TouchableOpacity
            style={styles.btn}
            onPress={openMapsNavigation}
            activeOpacity={0.8}
          >
            <Text style={styles.btnText}>Guide me home</Text>
          </TouchableOpacity>

          {/* TODO: remove this dev/test section before demo */}
          {__DEV__ && (
            <View style={styles.devSection}>
              <Text style={styles.devLabel}>Dev / Test</Text>
              <TouchableOpacity
                style={[styles.btn, styles.btnDev]}
                onPress={sendTestNotification}
                activeOpacity={0.8}
              >
                <Text style={styles.btnDevText}>Send test notification</Text>
              </TouchableOpacity>
              <Text style={styles.devHint}>
                Tap the test notification to verify deep-link routing to /alerts/test-id
              </Text>
            </View>
          )}
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
  fallbackNote: {
    fontSize: 13,
    color: '#94a3b8',
    fontStyle: 'italic',
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
  btnText: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '600',
  },
  devSection: {
    width: '100%',
    marginTop: 20,
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    backgroundColor: '#ffffff',
    alignItems: 'center',
  },
  devLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: '#94a3b8',
    textTransform: 'uppercase',
    marginBottom: 10,
  },
  btnDev: {
    backgroundColor: '#64748b',
    marginBottom: 8,
  },
  btnDevText: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: '600',
  },
  devHint: {
    fontSize: 12,
    color: '#94a3b8',
    textAlign: 'center',
  },
});
