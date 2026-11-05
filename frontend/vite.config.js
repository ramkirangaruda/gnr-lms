import { defineConfig } from 'vite';
import preact from '@preact/preset-vite';

// Builds tiny "islands" that enhance server-rendered Django pages.
// React Bits components run on Preact (preact/compat) – same API as React, ~10x smaller.
export default defineConfig({
  plugins: [preact()],
  base: '/static/islands/',
  build: {
    outDir: '../static/islands',
    emptyOutDir: true,
    target: 'es2019',
    cssCodeSplit: true,
    rollupOptions: {
      input: { islands: 'src/islands.js' },
      output: { entryFileNames: '[name].js', chunkFileNames: 'c/[name]-[hash].js', assetFileNames: 'c/[name]-[hash][extname]' }
    }
  }
});
