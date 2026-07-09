const path = require('path');
const Mocha = require('mocha');

function run() {
    const mocha = new Mocha({
        ui: 'tdd',
        color: true,
        timeout: 20000,
    });
    mocha.addFile(path.resolve(__dirname, 'smoke.test.js'));
    return new Promise((resolve, reject) => {
        mocha.run(failures => {
            if (failures > 0) {
                reject(new Error(`${failures} BEAST VS Code extension test(s) failed.`));
            } else {
                resolve();
            }
        });
    });
}

module.exports = { run };
