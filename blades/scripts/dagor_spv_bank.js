#!/usr/bin/env node
'use strict';
// Dagor compiledShaders/gameSpirV.ps50.shdump.bin:
// zlib envelope -> 116-byte header -> SMOL-V -> original SPIR-V.
// Match the exact sha256(SPIR-V)[:16] emitted by NXNative vkCreateShaderModule.
// This script runs on Linux/Colab too. Only final Metal translation needs macOS.
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const crypto = require('crypto');
const {default:decode, smolvDecodedSize} = require('../vendor/smolv_decode.js');
const MAGIC = 0x534d4f4c, SPIRV = 0x07230203;
const MAX_UNZIPPED = 7 * 1024 * 1024, MAX_SPIRV = 8 * 1024 * 1024;
const ZLIB = Buffer.from([0x78,0xda]), PADDING = Buffer.alloc(16);
function parseArgs(argv) {
  const args = {};
  for (let i=0;i<argv.length;i++) {
    let a=argv[i];
    if (a==='--all') {args.all=true;continue;}
    if (!['--dump','--output','--wanted','--report','--min-matches'].includes(a) || !argv[i+1])
      throw Error('invalid option '+a);
    args[a.slice(2).replace('-','_')] = argv[++i];
  }
  if (!args.dump||!args.output||(!args.wanted&&!args.all))
    throw Error('expected --dump --output and --wanted (or --all)');
  return args;
}
function wantedFrom(p) {
  const lines=fs.readFileSync(p,'utf8').split(/\r?\n/).map(x=>x.trim()).filter(x=>x&&!x.startsWith('#'));
  if (lines.some(x=>!/^[0-9a-f]{16}$/.test(x))) throw Error('invalid iPhone shader hash');
  const keys=new Set(lines);
  if (keys.size!==lines.length) throw Error('duplicate iPhone shader hash');
  return keys;
}
function scan(archive,output,wanted,all) {
  fs.mkdirSync(output,{recursive:true});
  const matches = new Set(), allkeys = new Set(), err = {};
  let candidates=0, records=0, decoded=0, failed=0;
  for (let at=archive.indexOf(ZLIB); at>=0; at=archive.indexOf(ZLIB,at+2)) {
    candidates++;
    let envelope;
    try {
      envelope=zlib.inflateSync(archive.subarray(at,Math.min(at+350000,archive.length)),
                                {maxOutputLength:MAX_UNZIPPED});
    }catch(e){continue;}
    if (envelope.length<140||envelope.readUInt32LE(116)!==MAGIC||
        envelope.readUInt32LE(112)!==envelope.length-116) continue;
    records++;
    try {
      const smol=envelope.subarray(116);
      const trim=smol.indexOf(PADDING,24);
      if (trim<25)throw Error('no 16-byte SMOL-V padding sentinel');
      const data=smol.subarray(0,trim);
      const outputSize=smolvDecodedSize(data.buffer,data.byteOffset,data.length);
      if (outputSize<20||outputSize>MAX_SPIRV||outputSize%4)throw Error('invalid SPIR-V size '+outputSize);
      const spv=Buffer.from(decode(data.buffer,data.byteOffset,data.length));
      if (spv.length!==outputSize||spv.readUInt32LE(0)!==SPIRV)throw Error('invalid SPIR-V magic/size');
      decoded++;
      const key=crypto.createHash('sha256').update(spv).digest('hex').slice(0,16);
      if (allkeys.has(key))continue;
      allkeys.add(key);
      if (all||wanted.has(key)) {
        fs.writeFileSync(path.join(output,key+'.spv'),spv);
        matches.add(key);
      }
    } catch(e) {
      failed++;
      const msg=String(e&&e.message||e).slice(0,160);err[msg]=(err[msg]||0)+1;
    }
  }
  return {candidateZlib:candidates,dagorRecords:records,decoded,decodeErrors:err,
    failedDecode:failed,uniqueDecoded:allkeys.size,requested:wanted.size,matched:matches.size,
    matches:[...matches].sort(),missing:[...wanted].filter(k=>!matches.has(k)).sort()};
}
function main() {
  const opts=parseArgs(process.argv.slice(2)),wanted=opts.wanted?wantedFrom(opts.wanted):new Set();
  const report=scan(fs.readFileSync(opts.dump),opts.output,wanted,Boolean(opts.all));
  const target=opts.report||path.join(opts.output,'dagor_shaders.json');
  fs.mkdirSync(path.dirname(target),{recursive:true});
  fs.writeFileSync(target,JSON.stringify({...report,source:path.basename(opts.dump)},null,2)+'\n');
  console.log('[BladesTime] Dagor: '+report.dagorRecords+' SMOL-V records, '+report.decoded+
    ' valid SPIR-V, '+report.matched+'/'+report.requested+' observed missing shader keys recovered.');
  if (report.missing.length)console.log('[BladesTime] Still missing keys: '+report.missing.join(' '));
  if (opts.min_matches && report.matched<Number(opts.min_matches))
    throw Error('insufficient exact shader hashes: '+report.matched+'/'+report.requested+
      '; refusing another incomplete 8-shader IPA');
}
if (require.main===module) {
  try{main();}catch(e){console.error('[BladesTime] ERROR:',e.stack||e);process.exitCode=1;}
}
module.exports={scan};