import { defineConfig } from 'vite';
import solid from 'vite-plugin-solid';

export default defineConfig({
  plugins: [solid()],
  server: {host: '127.0.0.1', port: 3001, strictPort: true,
    proxy: {'/api': 'http://127.0.0.1:15151', '/websocket': {target: 'ws://127.0.0.1:15151', ws: true}}},
});
