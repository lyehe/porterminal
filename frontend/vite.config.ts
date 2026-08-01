import { defineConfig, Plugin } from 'vite';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { readdirSync, unlinkSync, existsSync } from 'fs';

const frontendDir = fileURLToPath(new URL('.', import.meta.url));

/** Clean old generated JavaScript and CSS chunks before build. */
function cleanOldAssets(): Plugin {
  const assetsDir = resolve(frontendDir, '../porterminal/static/assets');
  const generatedPrefixes = ['app-', 'terminal-'];
  return {
    name: 'clean-old-assets',
    buildStart() {
      if (!existsSync(assetsDir)) return;
      for (const file of readdirSync(assetsDir)) {
        if (generatedPrefixes.some(prefix => file.startsWith(prefix)) &&
          (file.endsWith('.js') || file.endsWith('.css'))) {
          unlinkSync(resolve(assetsDir, file));
        }
      }
    },
  };
}

export default defineConfig(({ command }) => ({
    root: '.',
    base: '/static/',
    plugins: command === 'build' ? [cleanOldAssets()] : [],

  resolve: {
    alias: {
      '@': resolve(frontendDir, 'src'),
    },
  },

  build: {
    outDir: '../porterminal/static',
    emptyOutDir: false, // Preserve icons
    rollupOptions: {
      input: {
        app: resolve(frontendDir, 'index.html'),
      },
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]',
        manualChunks(id) {
          return id.includes('/node_modules/@xterm/') ? 'terminal' : undefined;
        },
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
}));
