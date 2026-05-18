import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  Image,
  ActivityIndicator,
} from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { COLORS } from '../../constants/theme';
import { getAlert, ackAlert, rewriteImagePath } from '../../lib/api';

export default function AlertDetailScreen() {
  const { id } = useLocalSearchParams();
  const [alert, setAlert] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [ackLoading, setAckLoading] = useState(false);

  useEffect(() => {
    if (!id) return;
    let mounted = true;
    getAlert(id)
      .then((data) => {
        if (mounted) setAlert(data);
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
  }, [id]);

  const handleAck = async (action) => {
    if (!id) return;
    setAckLoading(true);
    try {
      const updated = await ackAlert(id, action);
      setAlert(updated);
    } catch (e) {
      setError(e.message);
    } finally {
      setAckLoading(false);
    }
  };

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={COLORS.primary} />
      </View>
    );
  }

  if (error && !alert) {
    return (
      <View style={styles.center}>
        <Text style={styles.errorText}>{error}</Text>
      </View>
    );
  }

  if (!alert) {
    return (
      <View style={styles.center}>
        <Text style={styles.emptyText}>Alert not found.</Text>
      </View>
    );
  }

  const imageUri = rewriteImagePath(alert.image_path);
  const isClosed = alert.status === 'acknowledged' || alert.status === 'closed';

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.headerRow}>
        <View style={[styles.severityBadge, { backgroundColor: getSeverityColor(alert.severity) + '18' }]}>
          <Text style={[styles.severityText, { color: getSeverityColor(alert.severity) }]}>
            {alert.severity || 'medium'}
          </Text>
        </View>
        <Text style={styles.statusText}>{alert.status || 'open'}</Text>
      </View>

      <Text style={styles.title}>{alert.title || 'Alert'}</Text>
      <Text style={styles.body}>{alert.body || alert.detailed_explanation || ''}</Text>

      {alert.detailed_explanation && alert.body !== alert.detailed_explanation && (
        <Text style={styles.explanation}>{alert.detailed_explanation}</Text>
      )}

      {alert.recommended_action && (
        <View style={styles.infoBlock}>
          <Text style={styles.infoLabel}>Recommended Action</Text>
          <Text style={styles.infoValue}>{alert.recommended_action}</Text>
        </View>
      )}

      {alert.room_name && (
        <View style={styles.infoBlock}>
          <Text style={styles.infoLabel}>Room</Text>
          <Text style={styles.infoValue}>{alert.room_name}</Text>
        </View>
      )}

      {imageUri && (
        <Image source={{ uri: imageUri }} style={styles.image} resizeMode="cover" />
      )}

      {!isClosed && (
        <View style={styles.actions}>
          <TouchableOpacity
            style={[styles.btn, styles.btnOk]}
            onPress={() => handleAck('ok')}
            disabled={ackLoading}
            activeOpacity={0.8}
          >
            <Text style={styles.btnText}>I am OK</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.btn, styles.btnReturning]}
            onPress={() => handleAck('returning')}
            disabled={ackLoading}
            activeOpacity={0.8}
          >
            <Text style={styles.btnText}>I am returning</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.btn, styles.btnDismiss]}
            onPress={() => handleAck('dismissed')}
            disabled={ackLoading}
            activeOpacity={0.8}
          >
            <Text style={[styles.btnText, styles.btnDismissText]}>Dismiss</Text>
          </TouchableOpacity>
        </View>
      )}

      {isClosed && (
        <View style={styles.closedBanner}>
          <Text style={styles.closedText}>This alert has been acknowledged.</Text>
        </View>
      )}
    </ScrollView>
  );
}

function getSeverityColor(severity) {
  if (severity === 'high' || severity === 'critical') return '#ef4444';
  if (severity === 'medium') return '#f59e0b';
  if (severity === 'low') return '#3b82f6';
  return '#94a3b8';
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.bg,
  },
  content: {
    padding: 20,
    paddingBottom: 40,
  },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: COLORS.bg,
  },
  errorText: {
    color: '#ef4444',
    fontSize: 14,
  },
  emptyText: {
    color: COLORS.secondaryText,
    fontSize: 14,
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  severityBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 6,
  },
  severityText: {
    fontSize: 12,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  statusText: {
    fontSize: 12,
    color: '#94a3b8',
    textTransform: 'capitalize',
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
    color: COLORS.text,
    marginBottom: 10,
  },
  body: {
    fontSize: 15,
    color: '#334155',
    lineHeight: 22,
    marginBottom: 16,
  },
  explanation: {
    fontSize: 14,
    color: COLORS.secondaryText,
    lineHeight: 20,
    marginBottom: 16,
  },
  infoBlock: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 14,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: 'rgba(16, 185, 129, 0.08)',
  },
  infoLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: '#94a3b8',
    marginBottom: 4,
    textTransform: 'uppercase',
  },
  infoValue: {
    fontSize: 15,
    color: COLORS.text,
  },
  image: {
    width: '100%',
    height: 220,
    borderRadius: 16,
    marginVertical: 12,
    backgroundColor: '#e2e8f0',
  },
  actions: {
    gap: 10,
    marginTop: 8,
  },
  btn: {
    paddingVertical: 14,
    borderRadius: 12,
    alignItems: 'center',
  },
  btnOk: {
    backgroundColor: COLORS.primary,
  },
  btnReturning: {
    backgroundColor: '#3b82f6',
  },
  btnDismiss: {
    backgroundColor: '#ffffff',
    borderWidth: 1,
    borderColor: '#e2e8f0',
  },
  btnText: {
    color: '#ffffff',
    fontSize: 15,
    fontWeight: '600',
  },
  btnDismissText: {
    color: COLORS.text,
  },
  closedBanner: {
    marginTop: 12,
    padding: 14,
    backgroundColor: '#f0fdf4',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(16, 185, 129, 0.15)',
    alignItems: 'center',
  },
  closedText: {
    color: COLORS.primary,
    fontSize: 14,
    fontWeight: '500',
  },
});
