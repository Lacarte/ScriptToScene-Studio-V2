import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

const isProd = process.env.NODE_ENV === 'production'

export default defineConfig({
  plugins: [vue()],

  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },

  server: {
    port: 5174,
    proxy: {
      '/api': 'http://localhost:5050',
      '/output': 'http://localhost:5050',
      '/js': 'http://localhost:5050',
      '/css': 'http://localhost:5050',
      '/sounds': 'http://localhost:5050',
      '/static': 'http://localhost:5050',
    },
  },

  base: isProd ? '/vue/' : '/',

  build: {
    outDir: resolve(__dirname, '..', 'static', 'dist'),
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: 'js/[name]-[hash].js',
        chunkFileNames: 'js/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
})
