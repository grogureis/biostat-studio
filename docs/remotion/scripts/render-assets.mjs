import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('..', import.meta.url));
const cli = path.join(root, 'node_modules/@remotion/cli/remotion-cli.js');
const assets = [
  ['HeroEN', 'overview.png'], ['HeroTR', 'overview.tr.png'],
  ['WorkflowEN', 'workflow.png'], ['WorkflowTR', 'workflow.tr.png'],
  ['ReportEN', 'report.png'], ['ReportTR', 'report.tr.png'],
];
for (const [id, name] of assets) {
  execFileSync(process.execPath, [cli, 'still', 'src/index.ts', id, `../assets/${name}`], {
    cwd: root, stdio: 'inherit',
  });
}
