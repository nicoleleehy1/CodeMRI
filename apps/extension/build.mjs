import { build } from 'esbuild';
await build({ entryPoints:['src/extension.ts'], bundle:true, platform:'node', format:'cjs', external:['vscode'], outfile:'dist/extension.js', sourcemap:true });

await build({entryPoints:['media/graph.js'],bundle:true,platform:'browser',format:'iife',outfile:'media/graph.bundle.js'});
