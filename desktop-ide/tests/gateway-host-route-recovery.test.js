// Contract-level source check for stale-port swarm route recovery.
const fs = require('fs');
const path = require('path');

const source = fs.readFileSync(path.join(__dirname, '..', 'main', 'gateway-host.js'), 'utf8');

if (!source.includes('gateway route recovered after 404')) throw new Error('missing route recovery log');
if (!source.includes("/edgek\\/swarm\\/(?:run|golden-path)")) throw new Error('missing swarm route recovery guard');
if (!source.includes('__gatewayRecoveryAttempt')) throw new Error('missing bounded recovery guard');

console.log(JSON.stringify({ok:true, check:'stale-port swarm route recovery'}));
