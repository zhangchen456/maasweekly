FROM mcr.microsoft.com/playwright/python@sha256:9e85bdc9c6980dc230c17f3548acb8d2d73b2cb2d5f6e34e706e18464559ef63
COPY requirements.lock.txt /tmp/requirements.lock.txt
RUN pip install --no-cache-dir -r /tmp/requirements.lock.txt psycopg2-binary==2.9.13 \
 && groupadd --gid 979 maasdata && useradd --uid 993 --gid 979 --create-home maasdata
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/work/.home TZ=Asia/Shanghai
USER maasdata
WORKDIR /work
