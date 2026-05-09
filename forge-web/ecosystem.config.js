module.exports = {
  apps: [
    {
      name: 'forge-web',
      cwd: '/home/ubuntu/forge/forge-web',
      script: 'server.js',
      env: {
        NODE_ENV: 'production',
        PORT: '3000',
        PYTHON_API_BASE_URL: 'http://127.0.0.1:8001'
      }
    }
  ]
};