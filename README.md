# 错题集系统

一个帮助学生记录和复习错题的在线系统。

## 部署状态
最后更新：2024-01-28

## 功能特点
- 错题记录和管理
- 智能复习提醒
- 错题分析统计

## 技术栈
- 前端：Next.js + Tailwind CSS
- 后端：Node.js
- 数据库：MongoDB

## 功能特点

- 📝 图片上传错题
- 🔍 OCR智能识别题目
- ✏️ 在线编辑和管理
- 🤖 AI智能分析和知识点总结
- 👥 用户账号系统
- 📊 错题统计和分析

## 技术栈

- 前端：Next.js + TailwindCSS + Ant Design
- 后端：Node.js + Express
- 数据库：MySQL
- 缓存：Redis
- 云服务：腾讯云COS、腾讯云OCR
- AI服务：OpenAI API

## 开发环境要求

- Node.js >= 18
- MySQL >= 8.0
- Redis >= 6.0

## 本地开发

1. 克隆项目
```bash
git clone https://github.com/hyq19920217/cuotiji.git
cd cuotiji
```

2. 安装依赖
```bash
# 安装前端依赖
cd frontend
npm install

# 安装后端依赖
cd ../backend
npm install
```

3. 配置环境变量
- 复制 `.env.example` 到 `.env`
- 填写必要的环境变量

4. 启动开发服务器
```bash
# 前端开发服务器
cd frontend
npm run dev

# 后端开发服务器
cd backend
npm run dev
```

## 部署

项目使用 GitHub Actions 进行自动化部署，推送到 main 分支会自动触发部署流程。

## 许可证

MIT License 