# Comic Downloader MCP Agent

一个简化的漫画下载器MCP代理，基于JMComic-Crawler-Python项目的核心功能，提供下载和搜索功能，默认保存到桌面。

## 功能特点

- 简化的漫画下载功能
- 漫画搜索功能（按漫画名和作者名搜索）
- 获取漫画详情功能
- 默认保存到桌面
- 支持异步下载
- 提供HTTP API接口
- 支持下载状态查询
- 支持取消下载任务

## 安装依赖

```bash
pip install -r requirements.txt
```

## 启动服务器

```bash
python start_server.py
```

服务器将在 `http://localhost:8080` 启动。

## API接口

### 1. 下载漫画

**POST** `/download`

请求体：
```json
{
  "album_id": "漫画ID"
}
```

响应：
```json
{
  "success": true,
  "album_id": "漫画ID",
  "message": "下载完成",
  "album_title": "漫画标题",
  "album_author": "作者",
  "download_path": "下载路径"
}
```

### 2. 获取下载状态

**GET** `/status/{album_id}`

响应：
```json
{
  "status": "completed",
  "message": "下载完成",
  "progress": 100,
  "result": {
    "album_title": "漫画标题",
    "download_path": "下载路径"
  }
}
```

### 3. 取消下载

**POST** `/cancel`

请求体：
```json
{
  "album_id": "漫画ID"
}
```

响应：
```json
{
  "success": true,
  "message": "任务已取消"
}
```

### 4. 获取所有下载状态

**GET** `/status`

响应：
```json
{
  "task_id_1": {
    "status": "completed",
    "progress": 100,
    "message": "下载完成"
  },
  "task_id_2": {
    "status": "downloading",
    "progress": 50,
    "message": "正在下载"
  }
}
```

### 5. 搜索漫画

**POST** `/search/comic`

请求体：
```json
{
  "comic_name": "漫画名称",
  "page": 1
}
```

响应：
```json
{
  "success": true,
  "query_info": "漫画名: 无修正",
  "total": 100,
  "page": 5,
  "current_page": 1,
  "comics": [
    {
      "id": "123456",
      "title": "漫画标题",
      "tags": ["标签1", "标签2"],
      "url": "https://18comic.vip/album/123456/"
    }
  ],
  "message": "找到 20 个结果，共 100 个"
}
```

### 6. 搜索作者

**POST** `/search/author`

请求体：
```json
{
  "author_name": "作者名称",
  "page": 1
}
```

响应：
```json
{
  "success": true,
  "query_info": "作者: MANA",
  "total": 50,
  "page": 3,
  "current_page": 1,
  "comics": [
    {
      "id": "789012",
      "title": "作者作品1",
      "tags": ["标签1", "标签2"],
      "url": "https://18comic.vip/album/789012/"
    }
  ],
  "message": "找到 20 个结果，共 50 个"
}
```

### 7. 获取漫画详情

**GET** `/detail/{comic_id}`

响应：
```json
{
  "success": true,
  "comic": {
    "id": "123456",
    "title": "漫画标题",
    "author": "作者名",
    "tags": ["标签1", "标签2"],
    "description": "漫画描述",
    "page_count": 50,
    "pub_date": "2023-01-01",
    "update_date": "2023-01-15",
    "likes": 1000,
    "views": 5000,
    "comment_count": 100,
    "episode_count": 5,
    "url": "https://18comic.vip/album/123456/"
  }
}
```

### 8. 健康检查

**GET** `/health`

响应：
```json
{
  "status": "healthy",
  "service": "comic_downloader"
}
```

## 使用示例

### 使用curl下载漫画

```bash
curl -X POST "http://localhost:8080/download" \
     -H "Content-Type: application/json" \
     -d '{"album_id": "422866"}'
```

### 查询下载状态

```bash
curl "http://localhost:8080/status/422866"
```

### 取消下载

```bash
curl -X POST "http://localhost:8080/cancel" \
     -H "Content-Type: application/json" \
     -d '{"album_id": "422866"}'
```

### 搜索漫画

```bash
curl -X POST "http://localhost:8080/search/comic" \
     -H "Content-Type: application/json" \
     -d '{"comic_name": "无修正", "page": 1}'
```

### 搜索作者

```bash
curl -X POST "http://localhost:8080/search/author" \
     -H "Content-Type: application/json" \
     -d '{"author_name": "MANA", "page": 1}'
```

### 获取漫画详情

```bash
curl "http://localhost:8080/detail/123456"
```

## 配置说明

下载器使用以下默认配置：

- 保存位置：桌面
- 文件夹命名规则：使用漫画名称
- 图片下载线程数：10
- 章节下载线程数：3
- 客户端类型：API客户端
- 重试次数：3

## 注意事项

1. 确保原项目的依赖已正确安装
2. 下载的漫画会保存到桌面
3. 支持异步下载，可以同时下载多个漫画
4. 可以通过API查询下载进度
5. 支持取消正在进行的下载任务

## 错误处理

如果下载失败，API会返回错误信息：

```json
{
  "success": false,
  "album_id": "漫画ID",
  "message": "下载失败: 错误信息",
  "error": "具体错误信息"
}
```

## 搜索功能说明

搜索功能基于JMComic-Crawler-Python项目移植，支持以下功能：

- **按漫画名搜索**：搜索包含指定关键词的漫画
- **按作者名搜索**：搜索指定作者的所有作品
- **获取漫画详情**：根据漫画ID获取详细信息
- **按最新时间排序**：搜索结果按发布时间排序

搜索功能特点：
- 使用JMComic的API客户端
- 支持分页显示
- 返回漫画ID、标题、标签等信息
- 提供访问链接

## 开发说明

本项目基于JMComic-Crawler-Python项目的核心功能，保留了以下功能：

- 核心下载功能
- 简化的搜索功能（漫画名和作者名搜索）
- 获取漫画详情功能

移除了以下功能：
- 复杂的搜索参数（分类、时间筛选等）
- 登录功能
- 收藏夹功能
- 插件系统
- 复杂的配置选项

简化了使用流程，默认保存到桌面，提供基础的搜索和下载功能。 