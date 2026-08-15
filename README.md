# Web UI + Railway + 动态订阅生成

A portable Railway deployment variant derived from the verified production baseline.

---

# 🚀 Deploy on Railway

Portable deployment does not depend on a Railway Template. Every Railway user/account can deploy this repository independently.

<p align="center">
  <a href="https://railway.com/new/github?utm_source=github&utm_medium=readme&utm_campaign=railway-portable">
    <img src="https://railway.com/button.svg" alt="Deploy on Railway" width="260">
  </a>
</p>

---
# 进入后选择仓库并刷新网页；
<img width="1338" height="562" alt="image" src="https://github.com/user-attachments/assets/4bb8b5c0-49ec-4f2e-9a2e-0a0c397a5752" />


# Web UI + Railway + 动态订阅生成

```text
│
├── site/
│   └── index.html
│
├── scripts/
│   └── start.sh
│       ├── 检查 Railway 当前实例环境变量
│       ├── 检查 Public Domain
│       ├── 检查 TCP Proxy
│       ├── 检查 TCP Proxy Port
│       ├── 首次缺少 Networking → 明确退出
│       └── Networking 完整 → 正常启动
│
├── deploy/
│   ├── provision.sh
│   │   └── 不使用 Railway CLI / API Token
│   │       首次部署采用 Web UI 手动初始化
│   │
│   └── README.md
│       └── 首次部署操作说明
│
├── generate.py
│   └── 根据当前 Railway 实例动态生成
│       ├── Public Domain
│       ├── TCP Proxy Domain
│       ├── TCP Proxy Port
│       └── 订阅内容
│
├── Dockerfile
│   └── 容器构建入口
│
├── railway.toml
│   └── Railway 服务配置
│
└── README.md
    └── Deploy on Railway
```

## 核心运行链路

```text
README
  ↓
🚀 Deploy on Railway
  ↓
Railway Repository Picker
  ↓
Deploy Repo
  ↓
第一次构建 / 启动
  ↓
缺少 Networking
  ↓
允许第一次失败
  ↓
Settings → Networking
  │
  ├── Generate Domain
  │      Target Port = 8080
  │
  └── TCP Proxy
         Target Port = 8080
  ↓
Railway 动态生成
  │
  ├── *.up.railway.app
  │
  └── *.proxy.rlwy.net:*
  ↓
Deploy / Redeploy
  ↓
start.sh
  ↓
generate.py
  ↓
Xray Gateway
  ↓
正常运行
```

---

# 第一次部署初始化后，必须手动添加：

- Generate Domain
- TCP Proxy
- 端口：8080

<img width="759" height="233" alt="image" src="https://github.com/user-attachments/assets/88810187-bb2e-47ea-994c-547c83997e00" />

---

# Scale

## Regions & Replicas

选择部署国家，可以随时更换！

<img width="1368" height="786" alt="image" src="https://github.com/user-attachments/assets/c885ecdf-dfc8-439d-9dcb-058ac6d40e37" />

选择完成，点击左上角：Deploy

---

完成整个部署，获取订阅：

<img width="1447" height="748" alt="image" src="https://github.com/user-attachments/assets/9540145a-db55-4c0e-8ad9-28d729e3e5d1" />


输入以下命令获取订阅链接：

```bash
cat /data/subscription_url.txt
```
