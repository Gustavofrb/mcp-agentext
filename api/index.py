"""Entry point para o Vercel (serverless)."""

import sys
import os

# Adiciona o diretório raiz ao path para importar server.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import app
