import { defineConfig, Plugin } from 'vite';
import { resolve } from 'path';
import { readdirSync, unlinkSync, existsSync } from 'fs';

/** Clean old app-*.js and app-*.css before build */
function cleanOldAssets(): Plugin {
  const assetsDir = resolve(__dirname, '../porterminal/static/assets');
  return {
    name: 'clean-old-assets',
    buildStart() {
      if (!existsSync(assetsDir)) return;
      for (const file of readdirSync(assetsDir)) {
        if (file.startsWith('app-') && (file.endsWith('.js') || file.endsWith('.css'))) {
          unlinkSync(resolve(assetsDir, file));
        }
      }
    },
  };
}

export default defineConfig({
  root: '.',
  base: '/static/',
  plugins: [cleanOldAssets()],

  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },

  build: {
    outDir: '../porterminal/static',
    emptyOutDir: false, // Preserve icons
    rollupOptions: {
      input: {
        app: resolve(__dirname, 'index.html'),
      },
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]',
      },
    },
    manifest: true,
  },

  server: {
    port: 5173,
    proxy: {
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
      '/api': {
        target: 'http://localhost:8000',
      },
    },
  },
});
