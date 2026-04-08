importScripts('https://www.gstatic.com/firebasejs/8.10.1/firebase-app.js');
importScripts('https://www.gstatic.com/firebasejs/8.10.1/firebase-messaging.js');

// 👈 حط إعدادات الفايربيز بتاعتك هنا (هتلاقيها في إعدادات المشروع في فايربيز)
firebase.initializeApp({
    apiKey: "AIzaSyB5uFUb4LVwtFbESnx24OrIu2ag1WxSqEc",
    projectId: "elbazaar-1a371",
    messagingSenderId: "996850468337",
    appId: "1:996850468337:web:73302c14c47c5aaa693050"
});

const messaging = firebase.messaging();

// استقبال الإشعارات في الخلفية (Background)
messaging.onBackgroundMessage(function(payload) {
  console.log('[firebase-messaging-sw.js] Received background message ', payload);
  const notificationTitle = payload.notification.title;
  const notificationOptions = {
    body: payload.notification.body,
    icon: '/static/logo.png' // مسار لوجو موقعك
  };

  self.registration.showNotification(notificationTitle, notificationOptions);
});