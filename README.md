# 错题集管理系统

一个基于 Flask 的错题集管理系统，支持：
- OCR 识别（使用百度 OCR）
- 错题管理（增删改查）
- 知识点分析（使用 Deepseek API）
- 标签管理

## 功能特点
- 图片上传和 OCR 识别
- 错题内容编辑
- AI 分析知识点
- 标签化管理

## 技术栈
- 后端：Flask + SQLAlchemy + MySQL
- OCR：百度 OCR API
- AI：Deepseek API
- 部署：Supervisor + Nginx

## 部署说明
1. 安装依赖：`pip install -r requirements.txt`
2. 配置数据库：修改 config.py 中的数据库连接信息
3. 运行：`python app.py` 