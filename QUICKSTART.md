# 本地启动快速指引 (QUICKSTART)

本文档是面向 **开发者本地 Windows 环境** 的手把手配置说明。
按照顺序执行即可跑通「注册 → 创建知识库 → 上传文档 → 智能问答(SSE 流式)」MVP 全链路。

---

## ⏱️ 预计耗时

- 本地已有 MySQL / Python 3.10+ / Node 18+：**约 10 分钟**
- 使用 Docker Compose 一键起依赖：**约 5 分钟**

---

## 📋 步骤总览

| 步骤 | 内容 |
|------|------|
| 1 | 启动 MySQL 8 & （可选）Redis 7 |
| 2 | 创建数据库 `enterpri se_rag` |
| 3 | 配置后端 `server/.env` |
| 4 | 安装 Python 依赖并启动后端 |
| 5 | 验证后端：访问 `http://localhost:8000/docs` |
| 6 | 配置前端 `web/.env.development` |
| 7 | 安装前端依赖并启动 Vite |
| 8 | 验证前端：注册账号并登录 |
| 9 | （可选）一键容器化部署 |

---

## 步骤 1：启动 MySQL 8 & Redis 7

### 方式 A：使用 Docker Compose（推荐，最省心）

在项目根目录执行：

```powershell
# 只启动 MySQL + Redis（前后端手动跑，方便调试）
docker compose up -d mysql redis
```

容器起来后 MySQL 的默认连接信息：
- Host: `127.0.0.1`
- Port: `3306`
- User: `root`
- Password: `123456`（见 docker-compose.yml）

Redis 默认：
- Host: `127.0.0.1`
- Port: `6379`
- 无密码

### 方式 B：已有本地 MySQL

确保版本 ≥ 8.0，且允许 `utf8mb4`。若已启用了密码插件 **caching_sha2_password**，PyMySQL 可正常连接（requirements 用的 `pymysql` 已兼容）。

---

## 步骤 2：创建业务数据库

用任意 MySQL 客户端（Navicat / DBeaver / MySQL CLI）执行：

```sql
CREATE DATABASE IF NOT EXISTS enterprise_rag
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;
```

> 表结构无需手动创建，后端首次启动时会通过 `SQLAlchemy Base.metadata.create_all()` 自动建好（见 `app/main.py` lifespan）。

---

## 步骤 3：配置后端环境变量

进入 `server/` 目录：

```powershell
cd server
Copy-Item .env.example .env
```

然后用编辑器打开生成的 `server/.env`，**至少修改以下 3 处**：

| 变量 | 说明 | 示例 |
|------|------|------|
| `SECRET_KEY` | JWT 密钥，建议用随机字符串 | 见下命令生成 |
| `DB_PASSWORD` | MySQL root 密码 | `123456`（Docker 版） |
| `LLM_API_KEY` | 大模型 API Key（必填，否则后续 RAG 无法工作） | `sk-xxx` |

**生成安全 SECRET_KEY（复制其中一条执行）：**

```powershell
# 有 Python 的话
python -c "import secrets; print(secrets.token_hex(32))"

# 纯 PowerShell
-join ((48..57) + (65..90) + (97..122) | Get-Random -Count 40 | % {[char]$_})
```

**LLM 服务商快速对比**（更多请查看 `.env.example` 第六节）：

| 服务商 | 申请地址 | 国内可用 | 免费额度 |
|--------|----------|----------|----------|
| 通义千问 DashScope | https://dashscope.console.aliyun.com/ | ✅ | 个人有额度 |
| DeepSeek | https://platform.deepseek.com/ | ✅ | 新用户 500 万 token |
| 月之暗面 Kimi | https://platform.moonshot.cn/ | ✅ | 有体验额度 |
| 硅基流动 SiliconFlow | https://cloud.siliconflow.cn/ | ✅ | 注册送额度 |
| Ollama 本地 | https://ollama.com/download | ✅ | 永久免费（本地跑） |

> MVP 阶段对话接口有**模拟回答占位**，即便暂时不填 `LLM_API_KEY` 也可以先把前后端跑通，注册/登录/知识库/文档等模块不受影响。

---

## 步骤 4：安装后端依赖并启动

**强烈建议使用虚拟环境（避免污染全局 Python）：**

```powershell
cd server

# ---- 创建并激活虚拟环境（Windows PowerShell）----
python -m venv .venv
.\.venv\Scripts\Activate.ps1
# 若报 ExecutionPolicy，先执行：Set-ExecutionPolicy -Scope Process Bypass

# ---- 安装依赖 ----
pip install --upgrade pip
pip install -r requirements.txt
# （中国大陆用户建议加国内镜像： -i https://pypi.tuna.tsinghua.edu.cn/simple ）

# ---- 启动后端 ----
python run.py
```

正常启动日志末尾会看到：
```
Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

---

## 步骤 5：验证后端

浏览器访问 **http://localhost:8000/docs**，应能看到 Swagger UI：

1. 点击 `/health` → Try it out → Execute，预期返回 `status: ok`
2. 点击 `POST /api/v1/auth/register`，填入 JSON：
   ```json
   { "username": "admin", "password": "admin123" }
   ```
   Execute 后预期返回 code=0，且带 `access_token`

若此处成功则后端（鉴权/MySQL/路由）全部 OK。

---

## 步骤 6：配置前端环境变量

新开一个终端（后端不要关），进入 `web/`：

```powershell
cd web
Copy-Item .env.example .env.development
```

一般情况下 `.env.development` 的默认值就能用（后端走 Vite 代理），
**如非 8000 端口请修改 `VITE_API_TARGET`**。

---

## 步骤 7：安装前端依赖并启动 Vite

```powershell
cd web

# ---- 安装依赖（推荐 pnpm，也可用 npm / yarn）----
# 如没装 pnpm： npm i -g pnpm
pnpm install
# 或：npm install

# ---- 启动开发服务器 ----
pnpm dev
# 或：npm run dev
```

启动成功会看到：
```
  ➜  Local:   http://localhost:5173/
```

---

## 步骤 8：验证前端（端到端）

浏览器打开 **http://localhost:5173**：

1. **注册** → 用刚才的 `admin / admin123` 注册（或新账号）
2. **登录** → 进入主界面
3. **知识库管理** → 新建一个知识库，如「公司制度」
4. **上传文档** → 进入知识库详情，上传任意 `.md/.txt/.pdf/.docx`
5. **智能问答** → 新建对话，关联知识库，发送问题即可看到 SSE 流式打字机效果

> 注意：MVP 阶段 **RAG 检索与 LLM 生成还未接入**，回答是模拟文本，具体实现路线请查看 `server/app/rag/README.md`。后续你让我实现即可。

---

## 步骤 9（可选）：一键容器化启动全部（含前后端）

```powershell
# 回到项目根目录
cd ..

# 1. 先准备好环境文件
Copy-Item server\.env.example server\.env    # 修改 SECRET_KEY / LLM_API_KEY / DB_*
Copy-Item web\.env.example web\.env.development
# 容器内网络：server/.env 中
#   DB_HOST=mysql    （容器名）
#   REDIS_HOST=redis （容器名）

# 2. 构建并启动全部四个容器
docker compose up -d --build

# 3. 查看状态
docker compose ps

# 4. 访问
#    前端：http://localhost:5173
#    后端文档：http://localhost:8000/docs
#    健康检查：http://localhost:8000/health
```

---

## 🐛 常见问题排查

| 现象 | 可能原因 | 解决 |
|------|----------|------|
| 后端启动报 `Can't connect to MySQL` | MySQL 未启动 / DB_PASSWORD 错误 / 数据库没建 | 检查 docker compose ps 或 MySQL 客户端连通性 |
| 前端 API 请求报 `404 Not Found` / `502` | 后端没启动 或 VITE_API_TARGET 不正确 | 确保 http://localhost:8000/health 返回 ok |
| 登录报 `401` 或 `Invalid token` | SECRET_KEY 前后被改过导致旧 token 失效 | 清除 localStorage，重新登录 |
| 上传文件报 `不支持的文件格式` | 目前白名单：.pdf/.docx/.doc/.txt/.md/.markdown | 转换格式或在 `DocumentService.ALLOWED_EXTENSIONS` 添加 |
| Windows 激活 venv 报错 `ExecutionPolicy` | PowerShell 默认策略 | 执行 `Set-ExecutionPolicy -Scope Process Bypass` 再激活 |

如遇到本指引未覆盖的问题，欢迎告知具体报错信息。
