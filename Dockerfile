# 使用 Python 3.11 + 完整 Debian（bookworm）镜像
FROM python:3.11-bookworm

# 设置时区（按需改成 Asia/Shanghai 等）
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 可选：设置语言环境（防止一些工具中文乱码）
ENV LANG=C.UTF-8

# 设置工作目录
WORKDIR /app

# ---------- 换成清华 apt 镜像源 ----------
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources

# 安装常用系统工具（按需增删）
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        git \
        wget \
        procps \
        lsof \
        net-tools \
        iputils-ping \
        dnsutils \
        vim-tiny \
        ca-certificates \
        gnupg \
        # 常见网络/HTTP 工具（按需启用）
        # httpie \
        # jq \
        # unzip \
    && rm -rf /var/lib/apt/lists/*

# 设置 Python 环境变量
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

# ---------- 全局配置 pip 镜像源（不仅构建生效，进容器装包也生效） ----------
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip config set global.trusted-host mirrors.tuna.tsinghua.edu.cn

# 复制依赖文件（先复制以利用 Docker 缓存）
COPY pyproject.toml .


# 安装 Python 依赖（含开发依赖）
RUN pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --compile \
    -e ".[dev]"

# 复制项目代码
COPY . .

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1


# 入口
CMD ["python", "agent/main.py"]