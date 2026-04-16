module.exports = {
  apps: [
    {
      name: "rag-api",
      script: "/home/ubuntu/sikdorak/python_api/start.sh",
      interpreter: "bash",
      restart_delay: 3000,
      max_restarts: 5
    }
  ]
};
