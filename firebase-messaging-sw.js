importScripts("https://www.gstatic.com/firebasejs/10.8.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/10.8.0/firebase-messaging-compat.js");

// Initialize Firebase inside the Service Worker
firebase.initializeApp({
  apiKey: "AIzaSyCfVmrY2rJIGkMVocdarjbQ30rEh78MwmY",
  authDomain: "negocios-8e8a4.firebaseapp.com",
  databaseURL: "https://negocios-8e8a4-default-rtdb.asia-southeast1.firebasedatabase.app",
  projectId: "negocios-8e8a4",
  storageBucket: "negocios-8e8a4.firebasestorage.app",
  messagingSenderId: "298423907311",
  appId: "1:298423907311:web:92b79b23776a4f56557c1a"
});

const messaging = firebase.messaging();

// Handle background notifications when browser/tab is closed
messaging.onBackgroundMessage((payload) => {
  const title = payload.notification?.title || "🚨 Sentinel-HL Alert";
  const options = {
    body: payload.notification?.body || "Hazard threshold breached in your monitored sector.",
    icon: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png",
    tag: "sentinel-emergency-alert",
    renotify: true,
    requireInteraction: true
  };

  self.registration.showNotification(title, options);
});
