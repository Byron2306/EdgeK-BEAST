'use strict';

const fs = require('fs');
const path = require('path');
const yaml = require('js-yaml');

function readServiceRegistry(root) {
  try {
    return yaml.load(fs.readFileSync(path.join(root, '.byron', 'services.yaml'), 'utf8')) || {};
  } catch (_) {
    return {};
  }
}

function serviceRegistryGateway(root) {
  const config = readServiceRegistry(root);
  const upstream = config?.services?.beast?.upstream;
  if (/^(?:127\.0\.0\.1|\[::1\]):\d+$/.test(String(upstream || ''))) {
    return `http://${upstream}`;
  }
  return 'http://127.0.0.1:8101';
}

function serviceRegistryPort(root, serviceName, fallback) {
  const config = readServiceRegistry(root);
  const value = Number(config?.services?.[serviceName]?.port);
  return Number.isInteger(value) && value > 0 && value <= 65535 ? value : fallback;
}

module.exports = {
  readServiceRegistry,
  serviceRegistryGateway,
  serviceRegistryPort,
};
