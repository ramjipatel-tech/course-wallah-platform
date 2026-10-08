const express = require('express');
const path = require('path');
const { createProxyMiddleware } = require('http-proxy-middleware');

const app = express();
const PORT = process.env.PORT || 3000;
const API_BACKEND_URL = process.env.API_URL || 'http://127.0.0.1:8000';

// Proxy API requests to backend
app.use('/api', createProxyMiddleware({
  target: API_BACKEND_URL,
  changeOrigin: true,
  pathRewrite: {
    '^/api': '/api'
  }
}));

// Serve static assets
app.use('/static', express.static(path.join(__dirname, 'web', 'public')));

// SPA Fallback
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'web', 'public', 'index.html'));
});

app.listen(PORT, () => {
  console.log(`Course Wallah Dynamic Web Portal running on port ${PORT}`);
  console.log(`Proxying API requests to: ${API_BACKEND_URL}`);
});
