function t(lang, key) {
  const dict = {
    ru: {
      buy: 'Купить подписку',
      mySubscription: 'Моя подписка',
      myDevices: 'Мои устройства',
      downloadApp: 'Скачать приложение',
      support: 'Поддержка',
      language: 'Язык',
      welcome: 'Добро пожаловать в INET VPN',
      choosePlan: 'Выберите тариф:',
      devicesEmpty: 'У вас пока нет устройств.',
      supportText: 'Поддержка',
      downloadText: 'Скачать приложение',
      languageText: 'Выберите язык',
      subscriptionEmpty: 'Активная подписка не найдена.',
      paymentsDisabled: 'Оплата пока выключена. Модуль готов, но PAYMENTS_ENABLED=false.',
      paymentCreated: 'Платёж создан.',
      paymentFailed: 'Не удалось создать платёж.',
      languageSaved: 'Язык обновлён.',
      genericError: 'Произошла ошибка. Попробуйте ещё раз.',
    },
    en: {
      buy: 'Buy subscription',
      mySubscription: 'My subscription',
      myDevices: 'My devices',
      downloadApp: 'Download app',
      support: 'Support',
      language: 'Language',
      welcome: 'Welcome to INET VPN',
      choosePlan: 'Choose a plan:',
      devicesEmpty: 'No devices yet.',
      supportText: 'Support',
      downloadText: 'Download app',
      languageText: 'Choose language',
      subscriptionEmpty: 'No active subscription found.',
      paymentsDisabled: 'Payments are disabled for now. Module is ready, but PAYMENTS_ENABLED=false.',
      paymentCreated: 'Payment created.',
      paymentFailed: 'Failed to create payment.',
      languageSaved: 'Language updated.',
      genericError: 'Something went wrong. Please try again.',
    },
  };
  return (dict[lang] && dict[lang][key]) || dict.ru[key] || key;
}

module.exports = { t };
