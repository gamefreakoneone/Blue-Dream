import React from 'react';
import { View, Text, StyleSheet, Image } from 'react-native';
import { COLORS } from '../constants/theme';
import { rewriteImagePath } from '../lib/api';

export default function ChatBubble({ text, sender, imagePath }) {
  const isUser = sender === 'user';
  const resolvedImage = rewriteImagePath(imagePath);

  return (
    <View style={[styles.container, isUser ? styles.userAlign : styles.botAlign]}>
      <View style={[styles.bubble, isUser ? styles.userBubble : styles.botBubble]}>
        <Text style={[styles.text, isUser ? styles.userText : styles.botText]}>{text}</Text>
      </View>
      {resolvedImage && (
        <Image
          source={{ uri: resolvedImage }}
          style={styles.messageImage}
          resizeMode="cover"
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    maxWidth: '85%',
    marginVertical: 6,
  },
  userAlign: {
    alignSelf: 'flex-end',
    alignItems: 'flex-end',
  },
  botAlign: {
    alignSelf: 'flex-start',
    alignItems: 'flex-start',
  },
  bubble: {
    paddingVertical: 12,
    paddingHorizontal: 18,
    borderRadius: 22,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 1,
  },
  userBubble: {
    backgroundColor: COLORS.userBubble,
    borderBottomRightRadius: 6,
  },
  botBubble: {
    backgroundColor: COLORS.botBubble,
    borderBottomLeftRadius: 6,
    borderWidth: 1,
    borderColor: 'rgba(16, 185, 129, 0.06)',
  },
  text: {
    fontSize: 15,
    lineHeight: 22,
  },
  userText: {
    color: '#ffffff',
  },
  botText: {
    color: '#334155',
  },
  messageImage: {
    width: 260,
    height: 180,
    borderRadius: 16,
    marginTop: 8,
    backgroundColor: '#e2e8f0',
  },
});
