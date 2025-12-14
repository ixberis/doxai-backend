# Fuerza el event loop compatible en Windows para psycopg async
import sys, asyncio

if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        # Si ya hay un loop activo en algún contexto raro, ignoramos
        pass
# -*- coding: utf-8 -*-