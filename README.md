# Portable Railway + Xray XHTTP/REALITY

A portable Railway deployment variant derived from the verified production baseline.

## 🚀 Deploy on Railway

Portable deployment does not depend on a Railway Template. Every Railway user/account can deploy this repository independently.

<p align="center">
  <a href="https://railway.com/new/github?utm_source=github&utm_medium=readme&utm_campaign=railway-portable">
    <img src="https://railway.com/button.svg" alt="Deploy on Railway" width="260">
  </a>
</p>

# “Web UI + Railway 首次初始化 + Xray Gateway + 动态订阅生成” 四层：

Web UI + Railway 首次初始化 + Xray Gateway + 动态订阅生成
│
├── site/
│   └── index.html
│       └── 1440×900 Luxury Global Dashboard
│           ├── LONDON
│           ├── NEW YORK
│           ├── TOKYO
│           └── BEIJING ← 已改
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
核心运行链路
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
动态地址原则

现在最重要的是不保存固定实例地址：

RAILWAY_PUBLIC_DOMAIN
        ↓
https://<当前实例动态域名>/sub/<token>

以及：

RAILWAY_TCP_PROXY_DOMAIN
RAILWAY_TCP_PROXY_PORT
        ↓
http://<当前实例动态TCP域名>:<当前随机端口>/sub/<token>

因此：

PRIMARY
https://xxx.up.railway.app/sub/<token>


FALLBACK
http://xxx.proxy.rlwy.net:<RANDOM>/sub/<token>

这里的 xxx 和 <RANDOM> 都只是表示当前实例动态值的占位符，项目本身不写死它们。

订阅：
<img width="1098" height="203" alt="image" src="https://github.com/user-attachments/assets/4f31f732-0bbd-4894-9263-e9e5b2c54a8c" />
输入以下命令获取：
cat /data/subscription_url.txt
