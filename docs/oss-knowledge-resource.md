# 剧本文件包 OSS 接入

## 上传流程

1. 管理员或店长携带 Bearer JWT 调用 `POST /api/v1/knowledge/uploads/initiate`。
2. 后端创建知识资源、版本、文件清单和短期上传会话，并为每个文件生成 OSS V4 预签名 PUT URL。
3. 浏览器直接 PUT 文件到 OSS；AccessKey 永远不返回前端。
4. 前端调用 `POST /api/v1/knowledge/uploads/{upload_id}/complete`。
5. 后端逐个 HEAD 校验对象大小和可选 ETag，生成 `manifest.json`，再将该版本设为有效版本。
6. `GET /api/v1/knowledge/{document_id}/versions/{version_id}/manifest` 可导出标准清单，供迁移、归档和后续 RAG 入库使用。

## OSS Key 结构

```text
stores/{store_id}/knowledge/{document_id}/versions/{version_id}/
├── source/{用户选择文件夹中的相对路径}
└── manifest/manifest.json
```

对象键使用不可变 `version_id`，避免重名覆盖；数据库保存业务名称和版本标签。新增版本时传已有 `documentId`，旧版本文件继续保留，便于回滚和导出。

## 必需配置

复制 `.env.example` 后填写数据库、JWT 和 OSS 配置。`JWT_SECRET_KEY` 生产环境不少于 32 字节；接口只接受 JWT 中角色为 `admin` 或 `manager` 的用户，并从可信 claim 获取 `store_id`，不接受客户端自报门店 ID。

OSS Bucket 还需设置 CORS：

- Allowed Origins：前端正式域名和本地开发域名
- Allowed Methods：`PUT`、`GET`、`HEAD`
- Allowed Headers：`*`
- Expose Headers：`ETag`

RAM 权限按 Bucket 和 `stores/*` 前缀最小化授予对象写入、读取元数据和读取权限。线上建议进一步改为 ECS/RAM Role 或 STS，减少长期密钥风险。

## 数据表

- `knowledge_documents`：逻辑知识资源、资源类型和当前有效版本
- `knowledge_versions`：不可变版本记录、manifest 地址和处理状态
- `knowledge_files`：每个版本的文件、相对路径、对象键、大小和校验信息
- `knowledge_upload_sessions`：短期上传会话及完成状态

迁移命令：

```bash
uv run alembic upgrade head
```

## 后续 RAG 扩展点

完成上传后可把版本状态从 `uploaded` 推进到 `processing`、`ready` 或 `failed`。解析、切片、向量索引应始终绑定 `version_id`，查询时只使用 `knowledge_documents.active_version_id` 指向的版本，避免旧知识混入结果。
