const path = require('path');
const dotenv = require('dotenv');

dotenv.config({ path: process.env.ENV_FILE || path.join(process.cwd(), '.env') });

function readBool(name, fallback = false) {
  const raw = process.env[name];
  if (raw === undefined || raw === null || raw === '') return fallback;
  return ['1', 'true', 'yes', 'on'].includes(String(raw).trim().toLowerCase());
}

function readInt(name, fallback = 0) {
  const raw = process.env[name];
  const parsed = Number.parseInt(String(raw ?? ''), 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function readStr(name, fallback = '') {
  const raw = process.env[name];
  return raw === undefined || raw === null || raw === '' ? fallback : String(raw);
}

function buildPlanConfig({ prefix, sourceEnvKey, defaultCode, defaultNameRu, defaultNameEn }) {
  return {
    enabled: readBool(`${prefix}_ENABLED`, false),
    code: readStr(`${prefix}_CODE`, defaultCode),
    name_ru: readStr(`${prefix}_NAME_RU`, defaultNameRu),
    name_en: readStr(`${prefix}_NAME_EN`, defaultNameEn),
    price_rub: readInt(`${prefix}_PRICE_RUB`, 0),
    duration_days: readInt(`${prefix}_DURATION_DAYS`, 0),
    device_limit: readInt(`${prefix}_DEVICE_LIMIT`, readInt('VPN_DEFAULT_DEVICE_LIMIT', 2)),
    source_env_key: sourceEnvKey,
  };
}

const dailyPlan = buildPlanConfig({
  prefix: 'PLAN_DAILY',
  sourceEnvKey: 'PLAN_DAILY',
  defaultCode: 'daily',
  defaultNameRu: '1 день',
  defaultNameEn: '1 day',
});

const monthlyPlan = buildPlanConfig({
  prefix: 'PLAN_MONTHLY',
  sourceEnvKey: 'PLAN_MONTHLY',
  defaultCode: 'monthly',
  defaultNameRu: '30 дней',
  defaultNameEn: '30 days',
});

const config = {
  port: readInt('PORT', 3000),
  databaseUrl: readStr('DATABASE_URL', ''),
  jwtSecret: readStr('JWT_SECRET', 'replace-me'),
  corsOrigins: readStr('CORS_ORIGINS', '*'),
  auth: {
    allowDevCode: readBool('AUTH_ALLOW_DEV_CODE', true),
    devLoginCode: readStr('AUTH_DEV_LOGIN_CODE', '111111'),
  },
  app: {
    name: readStr('APP_NAME', 'INET'),
    env: readStr('APP_ENV', 'development'),
    langs: readStr('APP_LANGS', 'ru,en').split(',').map((v) => v.trim()).filter(Boolean),
    baseUrl: readStr('APP_BASE_URL', ''),
    adminPanelBaseUrl: readStr('ADMIN_PANEL_BASE_URL', ''),
    androidAppUrl: readStr('ANDROID_APP_URL', ''),
    iosAppUrl: readStr('IOS_APP_URL', ''),
  },
  admin: {
    user: readStr('ADMIN_BASIC_USER', 'admin'),
    pass: readStr('ADMIN_BASIC_PASS', 'change-me'),
  },
  bot: {
    token: readStr('BOT_TOKEN', ''),
    mode: readStr('BOT_MODE', 'polling'),
    username: readStr('BOT_USERNAME', 'inet_bot'),
    name: readStr('BOT_NAME', 'INET Bot'),
    webhookSecret: readStr('BOT_WEBHOOK_SECRET', ''),
    webhookPath: readStr('BOT_WEBHOOK_PATH', '/telegram/webhook'),
  },
  supportTelegramUrl: readStr('SUPPORT_TELEGRAM_URL', ''),
  vpn: {
    defaultDeviceLimit: readInt('VPN_DEFAULT_DEVICE_LIMIT', 2),
    maxDevicesPerAccount: readInt('VPN_MAX_DEVICES_PER_ACCOUNT', 2),
    maintenanceMode: readBool('VPN_MAINTENANCE_MODE', false),
    newActivationsEnabled: readBool('VPN_NEW_ACTIVATIONS_ENABLED', true),
    showDailyPlan: readBool('VPN_SHOW_DAILY_PLAN', true),
    showMonthlyPlan: readBool('VPN_SHOW_MONTHLY_PLAN', true),
    settingsEditable: readBool('VPN_SETTINGS_EDITABLE', false),
  },
  payments: {
    provider: readStr('PAYMENTS_PROVIDER', 'yookassa'),
    enabled: readBool('PAYMENTS_ENABLED', false),
    yookassaShopId: readStr('YOOKASSA_SHOP_ID', ''),
    yookassaSecretKey: readStr('YOOKASSA_SECRET_KEY', ''),
    returnUrl: readStr('YOOKASSA_RETURN_URL', ''),
    webhookUrl: readStr('YOOKASSA_WEBHOOK_URL', ''),
  },
  plans: [dailyPlan, monthlyPlan],
};

module.exports = { config, readBool, readInt, readStr };
