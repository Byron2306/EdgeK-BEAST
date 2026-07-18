const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');

suite('BEAST VS Code extension smoke', () => {
    test('registers core IDE commands', async () => {
        const extension = vscode.extensions.getExtension('edgek.edgek-beast');
        assert.ok(extension, 'BEAST extension should be installed in the extension host');
        await extension.activate();

        const commands = new Set(await vscode.commands.getCommands(true));
        for (const command of [
            'edgekBeast.diagnoseIdeShell',
            'edgekBeast.openIdeLog',
            'edgekBeast.openMissionControl',
            'edgekBeast.showAgentSessions',
            'edgekBeast.showAgentSessionDetail',
            'edgekBeast.createAgentSession',
            'edgekBeast.pauseAgentSession',
            'edgekBeast.resumeAgentSession',
            'edgekBeast.cancelAgentSession',
            'edgekBeast.agentSessionToSourcePlan',
            'edgekBeast.showWorktrees',
            'edgekBeast.createWorktreeMission',
            'edgekBeast.openWorktreeMission',
            'edgekBeast.runWorktreeVerifier',
            'edgekBeast.promoteWorktreeMission',
            'edgekBeast.closeWorktreeMission',
            'edgekBeast.openSourceWorkbench',
            'edgekBeast.selectAllHunks',
            'edgekBeast.clearHunks',
        ]) {
            assert.ok(commands.has(command), `${command} should be registered`);
        }
        fs.mkdirSync(path.resolve(__dirname, '..', '..', '.vscode-test'), { recursive: true });
        fs.writeFileSync(
            path.resolve(__dirname, '..', '..', '.vscode-test', 'last-smoke.json'),
            JSON.stringify({ ok: true, commandCount: commands.size }, null, 2)
        );
    });
});
