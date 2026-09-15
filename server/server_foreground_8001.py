"""固定入口：reload=False 单进程启动后端。
用法： .venv\Scripts\python.exe server_foreground_8001.py
（绕过 run.py 里的 APP_ENV=='development' 隐式打开 reload 的坑，保证新 retriever 代码一定加载）
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        workers=1,
        reload=False,
        log_level="info",
    )
