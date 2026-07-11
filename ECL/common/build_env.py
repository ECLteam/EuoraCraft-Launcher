# 构建时注入的硬编码环境变量
# 此文件由 CI/CD 在构建时覆盖，用于发布版本强制打包敏感配置
# 开发环境下保持空字符串，由 .env / .env.dev 接管

MICROSOFT_CLIENT_ID = ""
