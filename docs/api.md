# API 约定

记录路由版本、鉴权、响应格式、错误码和 SSE 事件协议。
# 认证

首次部署后，在后端目录创建管理员：

```bash
uv run python -m scripts.create_admin \
  --phone 13800000000 \
  --store-name '门店名称'
```

认证接口：

- `POST /api/v1/auth/login`：手机号密码登录，返回 Access Token 并写入 HttpOnly Refresh Cookie。
- `POST /api/v1/auth/register`：按 `registrationType` 注册：`user` 为无门店普通用户，`store` 创建门店及首个 manager，`dm` 必须使用一次性门店邀请码。
- `POST /api/v1/auth/dm-invites`：manager/admin 生成 7 天有效且仅可使用一次的 DM 邀请码；数据库只保存邀请码摘要。
- `POST /api/v1/auth/refresh`：轮换 Refresh Token，返回新 Access Token。
- `POST /api/v1/auth/logout`：撤销当前 Refresh Token 并清除 Cookie。
- `POST /api/v1/auth/change-password`：校验当前密码、更新 Argon2 哈希并撤销该用户全部登录。
- `GET /api/v1/auth/me`：获取当前用户及门店身份。

前端业务请求使用 `Authorization: Bearer <accessToken>`；Refresh Token 不可被 JavaScript 读取。
