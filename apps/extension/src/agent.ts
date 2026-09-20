import { spawn, ChildProcess } from 'node:child_process';
import { createInterface } from 'node:readline';

/** Run the installed, authenticated Codex CLI without a shell or approval bypass. */
export function runAgent(executable: string, root: string, prompt: string, session: string | undefined,
  event: (event: any) => void, readOnly = false): {child: ChildProcess; done: Promise<void>} {
  const args = ['-a','never','-s',readOnly?'read-only':'workspace-write','-c','sandbox_workspace_write.writable_roots=[]','exec','--json','--skip-git-repo-check', ...(session ? ['resume',session,'-'] : ['-'])];
  const child = spawn(executable, args, {cwd:root, shell:false, stdio:['pipe','pipe','pipe']});
  let errors = '';
  const lines = createInterface({input:child.stdout!});
  lines.on('line', line => { try { event(JSON.parse(line)); } catch { /* Ignore non-event output. */ } });
  child.stderr!.on('data', data => { errors=(errors+data.toString()).slice(-4000); });
  child.stdin!.on('error',()=>{});
  child.stdin!.end(prompt);
  const done = new Promise<void>((resolve,reject)=>{
    child.once('error', error => reject(new Error(`Cannot start Codex. Install it, run codex login, or set codemri.codexPath. ${error.message}`)));
    child.once('close', (code,signal) => {lines.close();code===0?resolve():reject(new Error(signal?'Agent stopped. Any partial edits remain proposals until approved.':errors||`Codex exited with code ${code}`));});
  });
  return {child,done};
}
