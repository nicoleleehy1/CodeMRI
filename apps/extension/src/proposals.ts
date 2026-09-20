import { TextDecoder } from 'node:util';
import { Buffer } from 'node:buffer';
import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import * as os from 'node:os';
import { randomUUID } from 'node:crypto';

export interface FileProposal { path:string; before:string|null; after:string|null; mode:number }
export interface Proposal { id:string; root:string; directory:string; files:FileProposal[] }
const excluded=new Set(['.git','.codemri','.codemri-preview','node_modules','.venv','__pycache__','.DS_Store']);
const decoder=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true});

async function filesAt(root:string, relative=''):Promise<Map<string,Buffer>> {
  const result=new Map<string,Buffer>();
  for(const entry of await fs.readdir(path.join(root,relative),{withFileTypes:true})) {
    if(excluded.has(entry.name)) continue;
    const name=path.join(relative,entry.name);
    if(entry.isSymbolicLink()) throw new Error(`Symbolic links are not supported in proposals: ${name}`);
    if(entry.isDirectory()) for(const [key,value] of await filesAt(root,name)) result.set(key,value);
    else if(entry.isFile()) result.set(name.split(path.sep).join('/'),await fs.readFile(path.join(root,name)));
  }
  return result;
}

export async function prepareProposal(root:string) {
  root=await fs.realpath(root);
  const directory=await fs.mkdtemp(path.join(os.tmpdir(),'codemri-proposal-'));
  const work=path.join(directory,'workspace');
  // No linked worktree or symlinks back into the real repository.
  await fs.cp(root,work,{recursive:true,filter:async source=>{
    if(source===root)return true;
    if(excluded.has(path.basename(source)))return false;
    return !(await fs.lstat(source)).isSymbolicLink();
  }});
  const before=await filesAt(work);
  return {directory,work,before,root};
}

export async function collectProposal(stage:Awaited<ReturnType<typeof prepareProposal>>):Promise<Proposal> {
  const after=await filesAt(stage.work), files:FileProposal[]=[];
  for(const name of new Set([...stage.before.keys(),...after.keys()])) {
    const a=stage.before.get(name),b=after.get(name);
    if(a?.equals(b??Buffer.alloc(0)) && b!==undefined)continue;
    if(!a && !b)continue;
    let before:string|null, next:string|null;
    try { before=a?decoder.decode(a):null;next=b?decoder.decode(b):null; }
    catch {throw new Error(`Cannot review binary changes to ${name}. The original workspace is unchanged.`);}
    if(before?.includes('\0')||next?.includes('\0'))throw new Error(`Cannot review binary changes to ${name}.`);
    const mode=(await fs.stat(path.join(stage.work,name)).catch(()=>({mode:0o644}))).mode & 0o777;
    files.push({path:name,before,after:next,mode});
  }
  return {id:randomUUID(),root:stage.root,directory:stage.directory,files};
}

export async function safeTarget(root:string,name:string) {
  if(!name || name.split(/[\\/]/).some(p=>p==='..'||excluded.has(p)) || path.isAbsolute(name))throw new Error('Invalid proposal path');
  const target=path.resolve(root,name);
  if(!target.startsWith(root+path.sep))throw new Error('Proposal is outside the repository');
  let current=root;
  for(const part of name.split('/')) {
    current=path.join(current,part);
    const stat=await fs.lstat(current).catch((error:NodeJS.ErrnoException)=>{if(error.code==='ENOENT')return undefined;throw error;});
    if(stat?.isSymbolicLink())throw new Error(`Refusing to overwrite a symbolic link: ${name}`);
  }
  return target;
}

export async function verifyProposal(root:string,file:FileProposal) {
  const target=await safeTarget(root,file.path);
  const actual=await fs.readFile(target).catch((error:NodeJS.ErrnoException)=>{if(error.code==='ENOENT')return null;throw error;});
  const expected=file.before===null?null:Buffer.from(file.before);
  if(actual===null?expected!==null:expected===null||!actual.equals(expected)) {
    throw new Error(`${file.path} changed since the proposal was created. Discard it and ask the agent again; your newer edits were preserved.`);
  }
  return target;
}

/** Only the explicit approval message handler may call this function. */
export async function applyFile(root:string,file:FileProposal) {
  const target=await verifyProposal(root,file);
  if(file.after===null)await fs.unlink(target);
  else {
    await fs.mkdir(path.dirname(target),{recursive:true});
    await fs.writeFile(target,file.after,{encoding:'utf8',mode:file.mode,flag:file.before===null?'wx':'w'});
  }
}

export async function persistProposal(proposal:Proposal) {
  const file=path.join(proposal.directory,'proposal.json');
  await fs.writeFile(file,JSON.stringify(proposal),{mode:0o600});
  return file;
}
