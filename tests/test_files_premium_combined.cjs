const fs=require('node:fs'),path=require('node:path');
if(!process.env.FILES_SOURCE_PATH||!process.env.PSD_SOURCE_ROOT)throw Error('Supply combined Files fixture and retained PSD source root.');
const original=fs.readFileSync,html=original(process.env.FILES_SOURCE_PATH,'utf8');
fs.readFileSync=function(file,...args){if(String(file).replaceAll('\\','/').endsWith('components/files_window/index.html'))return args[0]==='utf8'?html:Buffer.from(html);return original.call(this,file,...args);};
process.chdir(process.env.PSD_SOURCE_ROOT);require(path.join(process.cwd(),'tests/test_psd_modal_files_ui.cjs'));
