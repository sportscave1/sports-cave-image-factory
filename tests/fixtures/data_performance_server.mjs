// Disposable in-memory PostgreSQL/WASM protocol fixture. No files or live DB.
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
const modules = resolve(process.argv[2]);
const {PGlite} = await import(pathToFileURL(resolve(modules, '@electric-sql/pglite/dist/index.js')).href);
const {PGLiteSocketServer} = await import(pathToFileURL(resolve(modules, '@electric-sql/pglite-socket/dist/index.js')).href);
const db = await PGlite.create();
const server = new PGLiteSocketServer({db, host:'127.0.0.1', port:Number(process.argv[3]), maxConnections:12});
await server.start();
console.log('READY');
process.on('SIGTERM', async()=>{await server.stop(); await db.close(); process.exit(0);});
