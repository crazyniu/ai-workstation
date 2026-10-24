// Isolated local checks; no GitHub token or Claude/Codex model request.
import { Client } from '/opt/workstation/mcp/node_modules/@modelcontextprotocol/sdk/dist/esm/client/index.js';
import { StdioClientTransport } from '/opt/workstation/mcp/node_modules/@modelcontextprotocol/sdk/dist/esm/client/stdio.js';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

if (process.getuid() === 0) throw new Error('Run MCP checks as dev.');
const directory = await mkdtemp(join(tmpdir(), 'workstation-mcp-check-'));
const marker = 'WORKSTATION_MCP_BROWSER_PASS';
const cases = [
  ['context7', [], []],
  ['playwright', ['--executable-path', '/usr/bin/google-chrome-stable', '--headless', '--isolated', '--sandbox'], [
    ['browser_navigate', { url: `data:text/html,<html><body>${marker}</body></html>` }],
    ['browser_evaluate', { function: '() => document.body.innerText' }, marker],
  ]],
  ['chrome-devtools', ['--executablePath', '/usr/bin/google-chrome-stable', '--headless', '--isolated', '--no-usage-statistics', '--no-performance-crux'], [
    ['new_page', { url: `data:text/html,<html><body>${marker}</body></html>` }],
    ['evaluate_script', { function: '() => document.body.innerText' }, marker],
  ]],
  ['godot', [], [['get_godot_version', {}, '4.7.2']]],
  // Real scene edits additionally need an activated Editor and project bridge.
  ['unity', [], []],
];
if (process.argv.includes('--online')) {
  cases[0][2].push(['resolve-library-id', { libraryName: 'React', query: 'React useState documentation' }]);
}
try {
  for (const [name, args, calls] of cases) {
    const client = new Client({ name: 'workstation-build-smoke', version: '1.0.0' });
    const transport = new StdioClientTransport({
      command: '/usr/local/bin/workstation-mcp', args: [name, ...args], cwd: directory,
      env: { ...process.env, GODOT_PATH: '/usr/local/bin/godot', DISPLAY: ':1', LIBGL_ALWAYS_SOFTWARE: '1',
        ...(name === 'unity' ? { UNITY_MCP_SKIP_STARTUP_CONNECT: 'true' } : {}) },
      stderr: 'inherit',
    });
    try {
      await client.connect(transport);
      const listed = await client.listTools();
      if (!listed.tools.length) throw new Error(`${name}: empty tool list`);
      let selectedPageId;
      for (const [tool, arguments_, expected] of calls) {
        const callArguments = { ...arguments_ };
        if (name === 'chrome-devtools' && tool === 'evaluate_script') {
          if (!selectedPageId) throw new Error('chrome-devtools/new_page: selected page id missing');
          callArguments.pageId = selectedPageId;
        }
        const result = await client.callTool({ name: tool, arguments: callArguments }, undefined, { timeout: 90000 });
        if (result.isError) throw new Error(`${name}/${tool}: ${JSON.stringify(result.content)}`);
        if (name === 'chrome-devtools' && tool === 'new_page') {
          const text = result.content.filter(item => item.type === 'text').map(item => item.text).join('\n');
          const match = text.match(/(\d+):[^\n]*\[selected\]/);
          if (!match) throw new Error('chrome-devtools/new_page: selected page id missing');
          selectedPageId = Number(match[1]);
        }
        if (expected && !JSON.stringify(result.content).includes(expected)) throw new Error(`${name}/${tool}: expected marker missing`);
      }
      console.log(`PASS ${name}: ${listed.tools.length} tools; ${calls.length} calls`);
    } finally {
      await client.close();
    }
  }
} finally {
  await rm(directory, { recursive: true, force: true });
}
