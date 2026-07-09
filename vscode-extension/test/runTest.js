const path = require('path');
const { downloadAndUnzipVSCode, runTests } = require('@vscode/test-electron');

async function main() {
    const extensionDevelopmentPath = path.resolve(__dirname, '..');
    const extensionTestsPath = path.resolve(__dirname, 'suite', 'index.js');
    const downloadedPath = await downloadAndUnzipVSCode({
        version: process.env.VSCODE_TEST_VERSION || 'stable',
    });
    const vscodeExecutablePath = path.join(path.dirname(downloadedPath), 'bin', 'code');
    await runTests({
        vscodeExecutablePath,
        extensionDevelopmentPath,
        extensionTestsPath,
        launchArgs: ['--disable-extensions'],
    });
}

main().catch(error => {
    console.error(error);
    process.exit(1);
});
