import { mkdir, copyFile, readFile, writeFile, readdir } from 'node:fs/promises';
await mkdir('web/dist/sdk/core', {recursive: true});
for (const name of await readdir('dist')) if (name.endsWith('.js')) await copyFile('dist/' + name, 'web/dist/sdk/core/' + name);
await writeFile('web/dist/sdk/agent.js', (await readFile('client/agent.js', 'utf8')).replace('../dist/index.js', './core/index.js'));
