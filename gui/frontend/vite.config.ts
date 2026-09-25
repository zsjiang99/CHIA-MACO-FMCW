import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import {fileURLToPath, URL} from 'node:url';
export default defineConfig(({mode}) => {
  if (mode !== 'maco') throw new Error('Only the RACO app is included in this artifact');
  return {root:fileURLToPath(new URL(`../../chia-${mode}/gui`,import.meta.url)),plugins:[react()],
    resolve:{alias:{'react-dom':fileURLToPath(new URL('./node_modules/react-dom',import.meta.url)),react:fileURLToPath(new URL('./node_modules/react',import.meta.url))}},
    build:{outDir:'dist',emptyOutDir:true},server:{host:'127.0.0.1',port:mode==='maco'?5174:5175,
      fs:{allow:[fileURLToPath(new URL('../..',import.meta.url))]},
      proxy:{'/api':{target:`http://127.0.0.1:${mode==='maco'?8765:8766}`,changeOrigin:false}}}};
});
