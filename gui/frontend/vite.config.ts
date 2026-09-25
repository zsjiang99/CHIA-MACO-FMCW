import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import {fileURLToPath, URL} from 'node:url';
export default defineConfig(({mode}) => {
  if (mode !== 'raco') throw new Error('Only the RACO app is included in this artifact');
  return {root:fileURLToPath(new URL('../../chia-raco/gui',import.meta.url)),plugins:[react()],
    resolve:{alias:{'react-dom':fileURLToPath(new URL('./node_modules/react-dom',import.meta.url)),react:fileURLToPath(new URL('./node_modules/react',import.meta.url))}},
    build:{outDir:'dist',emptyOutDir:true},server:{host:'127.0.0.1',port:5174,
      fs:{allow:[fileURLToPath(new URL('../..',import.meta.url))]},
      proxy:{'/api':{target:'http://127.0.0.1:8765',changeOrigin:false}}}};
});
