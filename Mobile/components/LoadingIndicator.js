import React from 'react';
import { View, StyleSheet } from 'react-native';
import { COLORS } from '../constants/theme';

export default function LoadingIndicator() {
  return (
    <View style={styles.container}>
      <View style={styles.bubble}>
        <View style={styles.dot} />
        <View style={[styles.dot, styles.dotDelay1]} />
        <View style={[styles.dot, styles.dotDelay2]} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignSelf: 'flex-start',
    marginVertical: 6,
  },
  bubble: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 18,
    paddingHorizontal: 20,
    borderRadius: 22,
    backgroundColor: COLORS.botBubble,
    borderWidth: 1,
    borderColor: 'rgba(16, 185, 129, 0.06)',
    borderBottomLeftRadius: 6,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: COLORS.primary,
    opacity: 0.6,
  },
  dotDelay1: {
    opacity: 0.4,
  },
  dotDelay2: {
    opacity: 0.2,
  },
});
