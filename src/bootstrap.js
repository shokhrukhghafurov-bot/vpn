const { runMigrations } = require('./db');
const { syncPlansFromEnv } = require('./services/plans');
const { seedLocations } = require('./services/locations');

async function bootstrapApplication() {
  await runMigrations();
  await syncPlansFromEnv();
  await seedLocations();
}

module.exports = { bootstrapApplication };
