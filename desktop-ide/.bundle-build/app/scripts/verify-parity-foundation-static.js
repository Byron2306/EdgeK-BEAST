'use strict';
process.env.BEAST_VERIFY_LSP = '0';
process.env.BEAST_VERIFY_DAP = '0';
process.env.BEAST_VERIFY_KERNEL = '0';
require('./verify-ide-parity-foundation.js');
