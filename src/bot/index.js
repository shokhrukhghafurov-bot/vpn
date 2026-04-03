const { Telegraf, Markup } = require('telegraf');
const { config } = require('../config');
const { bootstrapApplication } = require('../bootstrap');
const { upsertTelegramUser, getUserByTelegramId, setUserLanguage } = require('../services/users');
const { getVisiblePlans } = require('../services/plans');
const { serializeCurrentSubscription } = require('../services/subscriptions');
const { listDevicesByUserId } = require('../services/devices');
const { createPayment } = require('../services/payments');
const { t } = require('./text');

function mainKeyboard(lang) {
  return Markup.keyboard([
    [t(lang, 'buy'), t(lang, 'mySubscription')],
    [t(lang, 'myDevices'), t(lang, 'downloadApp')],
    [t(lang, 'support'), t(lang, 'language')],
  ]).resize();
}

function appDownloadText() {
  const lines = [];
  if (config.app.androidAppUrl) lines.push(`Android: ${config.app.androidAppUrl}`);
  if (config.app.iosAppUrl) lines.push(`iPhone / iPad: ${config.app.iosAppUrl}`);
  return lines.join('\n') || 'App links are not configured yet.';
}

async function ensureTelegramUser(ctx) {
  const from = ctx.from || {};
  const existing = await getUserByTelegramId(from.id);
  if (existing) return existing;
  return upsertTelegramUser({
    telegram_id: from.id,
    username: from.username || null,
    first_name: from.first_name || null,
    last_name: from.last_name || null,
    language: from.language_code === 'en' ? 'en' : 'ru',
  });
}

async function safeReply(ctx, text, extra) {
  try {
    await ctx.reply(text, extra);
  } catch (error) {
    console.error('Telegram reply failed', error);
  }
}

async function startBot() {
  if (!config.bot.token) {
    throw new Error('BOT_TOKEN is required to run the Telegram bot');
  }

  await bootstrapApplication();
  const bot = new Telegraf(config.bot.token);

  bot.catch(async (error, ctx) => {
    console.error('Bot error', error);
    const lang = ctx?.from?.language_code === 'en' ? 'en' : 'ru';
    await safeReply(ctx, t(lang, 'genericError'), mainKeyboard(lang));
  });

  bot.start(async (ctx) => {
    const user = await ensureTelegramUser(ctx);
    await ctx.reply(`${t(user.language || 'ru', 'welcome')}\n@${config.bot.username}`, mainKeyboard(user.language || 'ru'));
  });

  bot.hears([/Купить подписку/i, /Buy subscription/i], async (ctx) => {
    const user = await ensureTelegramUser(ctx);
    const lang = user.language || 'ru';
    const plans = await getVisiblePlans();
    await ctx.reply(
      t(lang, 'choosePlan'),
      Markup.inlineKeyboard(
        plans.map((plan) => [
          Markup.button.callback(
            `${lang === 'ru' ? plan.name_ru : plan.name_en} - ${plan.price_rub} RUB`,
            `buy:${plan.id}`,
          ),
        ]),
      ),
    );
  });

  bot.hears([/Моя подписка/i, /My subscription/i], async (ctx) => {
    const user = await ensureTelegramUser(ctx);
    const lang = user.language || 'ru';
    const subscription = await serializeCurrentSubscription(user.id);
    if (!subscription) {
      await ctx.reply(t(lang, 'subscriptionEmpty'), mainKeyboard(lang));
      return;
    }
    await ctx.reply(
      `${lang === 'ru' ? 'Тариф' : 'Plan'}: ${lang === 'ru' ? subscription.plan.name_ru : subscription.plan.name_en}\n` +
      `${lang === 'ru' ? 'Истекает' : 'Expires'}: ${subscription.expires_at}\n` +
      `${lang === 'ru' ? 'Лимит устройств' : 'Device limit'}: ${subscription.plan.device_limit}`,
      mainKeyboard(lang),
    );
  });

  bot.hears([/Мои устройства/i, /My devices/i], async (ctx) => {
    const user = await ensureTelegramUser(ctx);
    const lang = user.language || 'ru';
    const devices = await listDevicesByUserId(user.id);
    if (!devices.length) {
      await ctx.reply(t(lang, 'devicesEmpty'), mainKeyboard(lang));
      return;
    }
    const text = devices
      .map((item, index) => `${index + 1}. ${item.platform} - ${item.device_name || item.device_fingerprint}`)
      .join('\n');
    await ctx.reply(text, mainKeyboard(lang));
  });

  bot.hears([/Скачать приложение/i, /Download app/i], async (ctx) => {
    const user = await ensureTelegramUser(ctx);
    const lang = user.language || 'ru';
    await ctx.reply(`${t(lang, 'downloadText')}:\n${appDownloadText()}`, mainKeyboard(lang));
  });

  bot.hears([/Поддержка/i, /Support/i], async (ctx) => {
    const user = await ensureTelegramUser(ctx);
    const lang = user.language || 'ru';
    await ctx.reply(`${t(lang, 'supportText')}: ${config.supportTelegramUrl || 'not configured'}`, mainKeyboard(lang));
  });

  bot.hears([/Язык/i, /Language/i], async (ctx) => {
    const user = await ensureTelegramUser(ctx);
    const lang = user.language || 'ru';
    await ctx.reply(
      t(lang, 'languageText'),
      Markup.inlineKeyboard([
        [Markup.button.callback('Русский', 'lang:ru'), Markup.button.callback('English', 'lang:en')],
      ]),
    );
  });

  bot.action(/^lang:(ru|en)$/, async (ctx) => {
    const user = await ensureTelegramUser(ctx);
    const lang = ctx.match[1];
    await setUserLanguage(user.id, lang);
    await ctx.answerCbQuery();
    await ctx.reply(t(lang, 'languageSaved'), mainKeyboard(lang));
  });

  bot.action(/^buy:(.+)$/, async (ctx) => {
    const user = await ensureTelegramUser(ctx);
    const lang = user.language || 'ru';
    const planId = ctx.match[1];
    await ctx.answerCbQuery();
    try {
      const payment = await createPayment({ userId: user.id, planId });
      if (!config.payments.enabled) {
        await ctx.reply(`${t(lang, 'paymentsDisabled')}\nID: ${payment.id}`, mainKeyboard(lang));
        return;
      }
      await ctx.reply(`${t(lang, 'paymentCreated')}\n${payment.checkout_url || payment.id}`, mainKeyboard(lang));
    } catch (error) {
      await ctx.reply(`${t(lang, 'paymentFailed')}\n${error.message}`, mainKeyboard(lang));
    }
  });

  await bot.launch();
  console.log('INET bot started');

  process.once('SIGINT', () => bot.stop('SIGINT'));
  process.once('SIGTERM', () => bot.stop('SIGTERM'));
}

if (require.main === module) {
  startBot().catch((error) => {
    console.error(error);
    process.exit(1);
  });
}

module.exports = { startBot };
