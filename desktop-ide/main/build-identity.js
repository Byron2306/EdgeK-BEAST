'use strict';

const fs = require('fs');
const path = require('path');

const FALLBACK_BUILD_IDENTITY = Object.freeze({
  schema: 'beast.build-identity.v1',
  product: 'BEAST IDE',
  product_version: '3.1.0-rc4',
  release_id: 'BEAST-IDE-3.1.0-RC4',
  desktop_runtime_build: '0.1.2-enterprise-control-plane',
  identity_digest: 'unavailable',
});

function loadBuildIdentity(baseDirectory = path.resolve(__dirname, '..')) {
  try {
    const identityPath = path.join(baseDirectory, 'BUILD_IDENTITY.json');
    const identity = JSON.parse(fs.readFileSync(identityPath, 'utf8'));
    if (identity?.schema !== 'beast.build-identity.v1') throw new Error('unsupported build identity schema');
    return Object.freeze(identity);
  } catch (_) {
    return FALLBACK_BUILD_IDENTITY;
  }
}

module.exports = { FALLBACK_BUILD_IDENTITY, loadBuildIdentity };
