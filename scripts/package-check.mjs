// Verify the packed artifact through consumer imports, not workspace source paths.
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {mkdtemp, mkdir, writeFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';

const root = resolve('.');
const temp = await mkdtemp(join(tmpdir(), 'singularity-package-'));
const env = {...process.env, npm_config_cache: join(temp, 'cache')};
try {
  const output = execFileSync('npm', ['pack', '--ignore-scripts', '--json', '--pack-destination', temp], {cwd: root, env, encoding: 'utf8'});
  const [pack] = JSON.parse(output);
  assert.equal(pack.name, 'fingerprint-singularity');
  assert(pack.files.some(f => f.path === 'client/agent.d.ts'));
  assert(pack.files.some(f => f.path === 'docs/assets/banner.svg'));
  assert(!pack.files.some(f => /(^|\/)(\.env|\.npmrc|artifacts|server|node_modules)(\/|$)/.test(f.path)));
  const consumer = join(temp, 'consumer');
  await mkdir(consumer);
  await writeFile(join(consumer, 'package.json'), JSON.stringify({private: true, type: 'module'}));
  execFileSync('npm', ['install', '--ignore-scripts', '--offline', '--no-audit', '--no-fund', '--package-lock=false', join(temp, pack.filename)], {cwd: consumer, env, stdio: 'pipe'});
  execFileSync(process.execPath, ['--input-type=module', '-e', `
    import assert from 'node:assert/strict';
    import {collect, digest, match, collectDetailed, digestDetailed, matchDetailed} from 'fingerprint-singularity';
    import {createAgent} from 'fingerprint-singularity/client';
    const snapshot = collect({scope:'package-test', environment:{platform:'MacIntel', hardwareConcurrency:8, deviceMemory:8, language:'en-US', timezone:'UTC'}});
    assert.match(await digest(snapshot), /^sg1_[a-f0-9]{64}$/);
    assert.equal(match(snapshot, [{id:'candidate',snapshot}]).candidateId, 'candidate');
    const detailed = await collectDetailed({scope:'package-test',environment:{platform:'MacIntel',hardwareConcurrency:8},probes:{gpu:()=>'gpu',fonts:()=>'fonts'}});
    assert.match(await digestDetailed(detailed), /^sg2_[a-f0-9]{64}$/);
    assert.equal(matchDetailed(detailed,[{id:'detailed',snapshot:detailed}]).candidateId,'detailed');
    assert.equal(typeof createAgent({publicKey:'pk_'+'a'.repeat(32),endpoint:'https://identity.example.com'}).identify, 'function');
  `], {cwd: consumer, env, stdio: 'pipe'});
  await writeFile(join(consumer, 'consumer.ts'), `
    import {collect, digest, match, type Candidate, type DetailedCandidate, collectDetailed, digestDetailed, matchDetailed} from 'fingerprint-singularity';
    import {createAgent} from 'fingerprint-singularity/client';
    const s = collect({scope:'app'});
    const c: Candidate[] = [{id:'candidate',snapshot:s}];
    const d = await collectDetailed({scope:'app'});
    const candidates: DetailedCandidate[] = [{id:'detailed',snapshot:d}];
    void digestDetailed(d); void matchDetailed(d,candidates);
    void createAgent({publicKey:'pk_'+'a'.repeat(32),mode:'legacy'});
    void digest(s); void match(s,c); void createAgent({publicKey:'pk_'+'a'.repeat(32)});
  `);
  execFileSync(process.execPath, [join(root, 'node_modules/typescript/bin/tsc'), '--strict', '--noEmit', '--module', 'NodeNext', '--target', 'ES2022', 'consumer.ts'], {cwd: consumer, env, stdio: 'pipe'});
  console.log(`PASS packed ${pack.name}@${pack.version}: offline install, core/client imports, identification and consumer types`);
} finally {
  await rm(temp, {recursive: true, force: true});
}
