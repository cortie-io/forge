#!/bin/bash
export PYTHONPATH=/home/ubuntu/sikdorak/python_api
export VIRTUAL_ENV=/home/ubuntu/sikdorak/.venv
export PATH=/home/ubuntu/sikdorak/.venv/bin:$PATH
export OLLAMA_HOST=http://100.79.44.109:11434
export OLLAMA_MODEL=gemma:latest
export OLLAMA_EMBED_MODEL=bge-m3:latest
export CHROMA_DB_DIR=/home/ubuntu/sikdorak/RAG/chroma_db_v18_final
export PDF_PATH='/home/ubuntu/sikdorak/RAG/네트워크관리사-압축됨.pdf'
export MD_PATH=/home/ubuntu/sikdorak/RAG/theory_only.md
cd /home/ubuntu/sikdorak/python_api
exec /home/ubuntu/sikdorak/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001 --proxy-headers
