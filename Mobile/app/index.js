import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  StatusBar,
} from 'react-native';
import { useFocusEffect } from 'expo-router';
import { COLORS } from '../constants/theme';
import { queryAssistant, resetConversation } from '../lib/api';
import { getOrCreateSessionId, resetSessionId } from '../lib/session';
import ChatBubble from '../components/ChatBubble';
import LoadingIndicator from '../components/LoadingIndicator';
import { NewChatContext } from './_layout';

export default function ChatScreen() {
  const [messages, setMessages] = useState([
    { id: 'welcome', text: 'Hello, I am Memoria. How can I assist you today?', sender: 'bot' },
  ]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const scrollViewRef = useRef(null);
  const inputRef = useRef(null);

  const { ref: signalRef } = React.useContext(NewChatContext);

  useEffect(() => {
    getOrCreateSessionId().then((id) => setSessionId(id));
  }, []);

  const scrollToBottom = useCallback(() => {
    scrollViewRef.current?.scrollToEnd({ animated: true });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading, scrollToBottom]);

  const handleReset = useCallback(async () => {
    const currentSession = sessionId;
    setMessages([
      { id: 'welcome', text: 'Hello, I am Memoria. How can I assist you today?', sender: 'bot' },
    ]);
    const next = await resetSessionId();
    setSessionId(next);
    if (currentSession) {
      try {
        await resetConversation({ session_id: currentSession });
      } catch (e) {
        console.error('Conversation reset failed:', e);
      }
    }
  }, [sessionId]);

  useEffect(() => {
    if (signalRef) {
      signalRef.current.callback = handleReset;
    }
    return () => {
      if (signalRef) {
        signalRef.current.callback = null;
      }
    };
  }, [handleReset, signalRef]);

  const handleSend = async () => {
    const text = inputText.trim();
    if (!text || !sessionId) return;

    const userMsg = { id: `u-${Date.now()}`, text, sender: 'user' };
    setMessages((prev) => [...prev, userMsg]);
    setInputText('');
    setLoading(true);

    try {
      const data = await queryAssistant({ query: text, session_id: sessionId });
      const botMsg = {
        id: `b-${Date.now()}`,
        text: data.text || 'No response.',
        sender: 'bot',
        imagePath: data.image_path || null,
      };
      setMessages((prev) => [...prev, botMsg]);
    } catch (error) {
      console.error('Query error:', error);
      setMessages((prev) => [
        ...prev,
        { id: `e-${Date.now()}`, text: `Error: ${error.message}`, sender: 'bot' },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
    >
      <StatusBar barStyle="dark-content" backgroundColor={COLORS.chatBg} />
      <ScrollView
        ref={scrollViewRef}
        style={styles.chatContainer}
        contentContainerStyle={styles.chatContent}
        keyboardShouldPersistTaps="handled"
      >
        {messages.map((msg) => (
          <ChatBubble
            key={msg.id}
            text={msg.text}
            sender={msg.sender}
            imagePath={msg.imagePath}
          />
        ))}
        {loading && <LoadingIndicator />}
      </ScrollView>

      <View style={styles.inputArea}>
        <View style={styles.inputRow}>
          <TextInput
            ref={inputRef}
            style={styles.input}
            placeholder="Ask Memoria anything..."
            placeholderTextColor="#94a3b8"
            value={inputText}
            onChangeText={setInputText}
            onSubmitEditing={handleSend}
            returnKeyType="send"
            autoCorrect={false}
            autoCapitalize="none"
          />
          <TouchableOpacity
            style={[styles.sendBtn, !inputText.trim() && styles.sendBtnDisabled]}
            onPress={handleSend}
            disabled={!inputText.trim()}
            activeOpacity={0.8}
          >
            <Text style={styles.sendBtnText}>➤</Text>
          </TouchableOpacity>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.bg,
  },
  chatContainer: {
    flex: 1,
    backgroundColor: COLORS.bg,
  },
  chatContent: {
    padding: 16,
    paddingBottom: 24,
  },
  inputArea: {
    backgroundColor: '#ffffff',
    borderTopWidth: 1,
    borderTopColor: COLORS.border,
    paddingHorizontal: 16,
    paddingVertical: 12,
    paddingBottom: Platform.OS === 'ios' ? 28 : 12,
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#f1f5f9',
    borderRadius: 28,
    paddingHorizontal: 6,
    paddingVertical: 4,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  input: {
    flex: 1,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 16,
    color: '#1e293b',
  },
  sendBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: COLORS.primary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  sendBtnDisabled: {
    backgroundColor: '#cbd5e1',
  },
  sendBtnText: {
    color: '#ffffff',
    fontSize: 16,
    marginLeft: 2,
  },
});
