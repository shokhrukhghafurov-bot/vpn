const path = require('path');
const express = require('express');
const cors = require('cors');
const morgan = require('morgan');
const { config } = require('./config');
const { bootstrapApplication } = require('./bootstrap');
const publicRoutes = require('./routes/public');
const adminVpnRoutes = require('./routes/adminVpn');
const { errorHandler } = require('./middleware/errorHandler');

async function createApp() {
  await bootstrapApplication();

  const app = express();
  const corsOrigins = config.corsOrigins === '*'
    ? true
    : config.corsOrigins.split(',').map((item) => item.trim()).filter(Boolean);

  app.use(cors({ origin: corsOrigins, credentials: true }));
  app.use(express.json({ limit: '2mb' }));
  app.use(express.urlencoded({ extended: true }));
  app.use(morgan('dev'));

  app.use('/admin', express.static(path.join(process.cwd(), 'admin')));
  app.use('/', publicRoutes);
  app.use('/api/infra/admin/vpn', adminVpnRoutes);

  app.use(errorHandler);
  return app;
}

async function start() {
  const app = await createApp();
  app.listen(config.port, () => {
    console.log(`INET API listening on :${config.port}`);
  });
}

if (require.main === module) {
  start().catch((error) => {
    console.error(error);
    process.exit(1);
  });
}

module.exports = { createApp };
