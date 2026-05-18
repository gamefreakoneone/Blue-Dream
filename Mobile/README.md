# Memoria Mobile App

Expo React Native patient app for Project Memoria.

## Development with Expo Go

Use Expo Go for fast UI iteration, local notification testing, deep-link verification, and chat over LAN Wi-Fi.

1. Ensure your backend is running and accessible on the LAN.
2. Set `EXPO_PUBLIC_API_BASE_URL` in `Mobile/.env` (e.g., `http://192.168.1.112:8000`).
3. Start the Metro bundler:
   ```powershell
   cd Mobile
   npx expo start
   ```
4. Scan the QR code with the Expo Go app on your Android phone.

**Note:** Expo Go on Android SDK 54+ does **not** support remote push notifications. Local notifications and deep-link routing still work for testing.

## Real Push Notifications (EAS Development Build + Firebase)

To test backend-triggered emergency push notifications via Firebase Cloud Messaging (FCM):

1. Download your Firebase `google-services.json` and place it at `Mobile/google-services.json`.
2. Ensure `Mobile/app.json` includes:
   - `android.package`: `com.amogh.memoria`
   - `android.googleServicesFile`: `./google-services.json`
3. In `Mobile/lib/notifications.js`, set `USE_FCM = true`.
4. Build and install an EAS development build (see commands below).
5. The app will register the device with `push_provider: "fcm"` and an FCM token.

## Backend Environment Variables for FCM

Add these to your backend `.env`:

```env
FIREBASE_PROJECT_ID=<firebase-project-id>
FIREBASE_CREDENTIALS_PATH=C:\Users\amogh\Desktop\Blue-Dream\firebase-service-account.json
FIREBASE_ANDROID_PACKAGE=com.amogh.memoria
```

- `google-services.json` is for the **Android app build** only.
- The backend needs a separate **Firebase service account JSON** to send pushes via the FCM HTTP v1 API.
