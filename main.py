from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import func
from fastapi import FastAPI
from pydantic import BaseModel
import requests
import time
import os
import logging
from fastapi import HTTPException
from datetime import datetime, timedelta
from sqlalchemy import DateTime
from fastapi.responses import HTMLResponse
import httpx
import asyncio

COOLDOWN = timedelta(minutes=5)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class CheckResult(Base):
    __tablename__ = "checks"
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String)
    status_code = Column(Integer)
    latency_ms = Column(Integer)
    is_up = Column(Boolean)

    checked_at = Column(DateTime, default=datetime.utcnow) 
    last_alerted_at = Column(DateTime, nullable=True)


class TargetModel(Base):
    __tablename__ = "targets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    url = Column(String)

Base.metadata.create_all(bind=engine)


class Target(BaseModel):
    name: str
    url: str

app = FastAPI()
targets = []


@app.get("/", response_class=HTMLResponse)
def dashboard():
    db = SessionLocal()
    targets = db.query(TargetModel).all()
    rows = []

    for target in targets:
        checks = (
            db.query(CheckResult)
            .filter(CheckResult.url == target.url)
            .order_by(CheckResult.id.desc())
            .limit(10)
            .all()
        )

        latest = checks[0] if checks else None

        status = "PENDING"
        status_class = "unknown"
        latency = "-"
        uptime = "Waiting"
        hint = "Waiting for first check..."
        latency_class = "unknown"
        last_time = "-"

        if latest:
            if latest.is_up:
                status = "UP"
                status_class = "up"
            else:
                status = "DOWN"
                status_class = "down"

            latency = f"{latest.latency_ms}ms" if latest.latency_ms else "-"
            hint = "Latest check recorded"
            last_time = latest.checked_at.strftime("%H:%M:%S") if latest.checked_at else "-"

            if latest.latency_ms:
                latency_class = "slow" if latest.latency_ms > 1000 else "fast"

        if checks:
            if len(checks) >= 3:
                up_count = sum(1 for c in checks if c.is_up)
                uptime_percent = (up_count / len(checks)) * 100
                uptime = f"{uptime_percent:.1f}%"
            else:
                uptime = "Calculating..."

        rows.append(f"""
        <a href="/dashboard/{target.id}" style="text-decoration: none; color: inherit;">
            <div class="card">
                <div class="card-header">
                    <div class="name">{target.name}</div>
                    <div class="status {status_class}">{status}</div>
                </div>

                <div class="url">{target.url}</div>
                <div class="hint">{hint}</div>
                {"<div class='hint'>Last checked: " + last_time + "</div>" if latest else ""}

                {"<div class='empty-state'>No checks yet</div>" if not latest else ""}

                <div class="metrics">
                    <div class="metric">
                        <div class="metric-label">Latency</div>
                        <div class="metric-value {latency_class}">{latency}</div>
                    </div>

                    <div class="metric">
                        <div class="metric-label">Uptime</div>
                        <div class="metric-value">{uptime}</div>
                    </div>
                </div>
            </div>
        </a>
        """)

    db.close()

    return f"""
    <html>
        <head>
    
            <title>Uptime Monitor</title>
            <meta http-equiv="refresh" content="10">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 40px;
                    background: #f7f7f7;
                }}
                
                .grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                    gap: 20px;
                }}

                .card {{
                    background: white;
                    border-radius: 14px;
                    padding: 20px;
                    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08);
                    border: 1px solid #e5e5e5;
                }}

                h1 {{
                    margin-bottom: 24px;
                }}

                table {{
                    border-collapse: collapse;
                    width: 100%;
                    background: white;
                }}

                th, td {{
                    padding: 12px;
                    border-bottom: 1px solid #ddd;
                    text-align: left;
                }}

                th {{
                    background: #f0f0f0;
                }}

                .up {{
                    color: green;
                    font-weight: bold;
                }}

                .down {{
                color: white;
                background: #ff4d4f;
                }}

                .unknown {{
                    color: gray;
                    font-weight: bold;
                }}

                a {{
                    display: inline-block;
                    margin-top: 20px;
                }}
                .card-header {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 12px;
                }}

                .name {{
                    font-size: 20px;
                    font-weight: bold;
                }}

                .status {{
                    padding: 4px 10px;
                    border-radius: 999px;
                    font-size: 13px;
                    font-weight: bold;
                }}

                .url {{
                    color: #666;
                    font-size: 14px;
                    word-break: break-all;
                    margin-bottom: 16px;
                }}

                .metrics {{
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 12px;
                }}

                .metric {{
                    background: #f7f7f7;
                    border-radius: 10px;
                    padding: 12px;
                }}

                .metric-label {{
                    color: #777;
                    font-size: 12px;
                    margin-bottom: 4px;
                }}

                .metric-value {{
                    font-size: 18px;
                    font-weight: bold;
                }}
                .hint {{
                color: #999;
                font-size: 13px;
                margin-bottom: 16px;
                }}
                .empty-state {{
                color: #999;
                font-size: 14px;
                margin-bottom: 14px;
                font-style: italic;
            }}
            </style>
        </head>
        <body>
            <h1>Uptime Monitor</h1>
            <div class="subtitle">Live service health dashboard. Auto-refreshes every 10 seconds.</div>

            <div class="grid">
                {''.join(rows)}
            </div>

            <div class="actions">
                <a href="/docs">API Docs</a>
            </div>
        </body>
    </html>
    """
@app.get("/dashboard/{target_id}", response_class=HTMLResponse)
def target_detail(target_id: int):
    db = SessionLocal()

    target = db.query(TargetModel).filter(TargetModel.id == target_id).first()

    if not target:
        return "<h1>Target not found</h1>"

    checks = (
        db.query(CheckResult)
        .filter(CheckResult.url == target.url)
        .order_by(CheckResult.id.desc())
        .limit(10)
        .all()
    )

    rows = []

    for c in checks:
        status = "UP" if c.is_up else "DOWN"
        status_class = "up" if c.is_up else "down"
        latency = f"{c.latency_ms}ms" if c.latency_ms else "-"
        time = c.checked_at.strftime("%H:%M:%S") if c.checked_at else "-"

        rows.append(f"""
        <tr>
            <td>{time}</td>
            <td class="{status_class}">{status}</td>
            <td>{latency}</td>
        </tr>
        """)

    db.close()

    return f"""
    <html>
        <head>
            <title>Uptime Monitor</title>
            <meta http-equiv="refresh" content="10">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 40px;
                    background: #f5f5f5;
                    color: #111;
                }}

                h1 {{
                    margin-bottom: 8px;
                }}

                .subtitle {{
                    color: #666;
                    margin-bottom: 32px;
                }}

                .grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                    gap: 20px;
                }}

                .card {{
                    background: white;
                    border-radius: 14px;
                    padding: 20px;
                    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08);
                    border: 1px solid #e5e5e5;
                }}

                .card-header {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 12px;
                }}

                .name {{
                    font-size: 20px;
                    font-weight: bold;
                }}

                .status {{
                    padding: 4px 10px;
                    border-radius: 999px;
                    font-size: 13px;
                    font-weight: bold;
                }}

                .up {{
                    color: #0f7a32;
                    background: #dff7e7;
                }}

                .down {{
                    color: #a40000;
                    background: #ffe1e1;
                }}

                .unknown {{
                    color: #555;
                    background: #eeeeee;
                }}

                .url {{
                    color: #666;
                    font-size: 14px;
                    word-break: break-all;
                    margin-bottom: 16px;
                }}

                .metrics {{
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 12px;
                }}

                .metric {{
                    background: #f7f7f7;
                    border-radius: 10px;
                    padding: 12px;
                }}

                .metric-label {{
                    color: #777;
                    font-size: 12px;
                    margin-bottom: 4px;
                }}

                .metric-value {{
                    font-size: 18px;
                    font-weight: bold;
                }}

                .actions {{
                    margin-top: 32px;
                }}

                a {{
                    color: #333;
                }}
            </style>
        </head>
        <body>
            <h1>Uptime Monitor</h1>
            <div class="subtitle">Live service health dashboard. Auto-refreshes every 10 seconds.</div>

            <div class="grid">
                {''.join(rows)}
            </div>

            <div class="actions">
                <a href="/docs">API Docs</a>
            </div>
        </body>
    </html>
    """

@app.get("/checks")
def get_checks():
    db = SessionLocal()
    rows = db.query(CheckResult).order_by(CheckResult.id.desc()).limit(20).all()

    return [
        {
            "id": row.id,
            "url": row.url,
            "status_code": row.status_code,
            "latency_ms": row.latency_ms,
            "is_up": row.is_up
        }
        for row in rows
    ]


@app.post("/targets")
def add_target(target: Target):
    db = SessionLocal()

    existing = db.query(TargetModel).filter(TargetModel.url == target.url).first()

    if existing:
        db.close()
        raise HTTPException(
            status_code=400,
            detail="target url already exists"
        )

    row = TargetModel(
        name=target.name,
        url=target.url
    )

    db.add(row)
    db.commit()

    result = {
        "id": row.id,
        "name": row.name,
        "url": row.url
    }

    db.close()
    return result


@app.get("/targets")
def get_targets():
    db = SessionLocal()

    rows = db.query(TargetModel).order_by(TargetModel.id.desc()).all()

    result = [
        {
            "id": row.id,
            "name": row.name,
            "url": row.url
        }
        for row in rows
    ]

    db.close()
    return result


@app.post("/check")
def check_url(url: str):
    result = save_check_result(url)
    return result
        
def get_last_status(db, url: str):
    last = (
        db.query(CheckResult)
        .filter(CheckResult.url == url)
        .order_by(CheckResult.id.desc())
        .first()
    )
    return last

@app.delete("/targets/{target_id}")
def delete_target(target_id: int):
    db = SessionLocal()

    target = db.query(TargetModel).filter(TargetModel.id == target_id).first()

    if not target:
        db.close()
        raise HTTPException(status_code=404, detail="target not found")

    db.delete(target)
    db.commit()
    db.close()

    return {
        "message": "target deleted",
        "target_id": target_id
    }


@app.put("/targets/{target_id}")
def update_target(target_id: int, target: Target):
    db = SessionLocal()

    row = db.query(TargetModel).filter(TargetModel.id == target_id).first()

    if not row:
        db.close()
        raise HTTPException(status_code=404, detail="target not found")

    existing = (
        db.query(TargetModel)
        .filter(TargetModel.url == target.url, TargetModel.id != target_id)
        .first()
    )

    if existing:
        db.close()
        raise HTTPException(
            status_code=400,
            detail="target url already exists"
        )

    row.name = target.name
    row.url = target.url

    db.commit()

    result = {
        "id": row.id,
        "name": row.name,
        "url": row.url
    }

    db.close()
    return result

def request_with_retry(url: str, retries: int = 3, timeout: int = 3):
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, timeout=timeout)
            return response, attempt

        except requests.RequestException as e:
            last_error = e
            logging.warning(f"[RETRY] {url} attempt {attempt}/{retries} failed: {e}")
            time.sleep(1)

    raise last_error

async def async_request_with_retry(url: str, retries: int = 3, timeout: int = 3):
    last_error = None

    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(1, retries + 1):
            try:
                response = await client.get(url)
                return response, attempt

            except httpx.RequestError as e:
                last_error = e
                logging.warning(f"[RETRY] {url} attempt {attempt}/{retries} failed: {e}")
                await asyncio.sleep(1)

    raise last_error

def save_check_result(url: str):
    now = datetime.utcnow()
    logging.info(f"[CHECKING] {url}")

    db = SessionLocal()
    start = time.time()

    try:
        res, attempts = request_with_retry(url)
        latency = int((time.time() - start) * 1000)

        is_up = res.status_code == 200

        logging.info(f"[SUCCESS] {url} checked after {attempts} attempt(s)")

        row = CheckResult(
            url=url,
            status_code=res.status_code,
            latency_ms=latency,
            is_up=is_up
        )

    except requests.RequestException:
        is_up = False

        row = CheckResult(
            url=url,
            status_code=None,
            latency_ms=None,
            is_up=False
        )

    # 이전 상태 가져오기
    last = (
        db.query(CheckResult)
        .filter(CheckResult.url == url)
        .order_by(CheckResult.id.desc())
        .first()
    )

    # 상태 변화 감지
    if last:
        if last.is_up and not is_up:
            if not last.last_alerted_at or (now - last.last_alerted_at > COOLDOWN):
                logging.error(f"[ALERT] {url} went DOWN")
                send_discord_alert(f"🚨 DOWN: {url}")
                row.last_alerted_at = now

        elif not last.is_up and is_up:
            logging.info(f"[RECOVER] {url} is back UP")
            send_discord_alert(f"✅ RECOVERED: {url}")

        else:
            logging.info(f"[NO CHANGE] {url} is still {'UP' if is_up else 'DOWN'}")
    else:
        logging.info(f"[FIRST CHECK] {url} is {'UP' if is_up else 'DOWN'}")


    # 실패 로그
    if not is_up:
        logging.warning(f"[DOWN] {url} is down")

    db.add(row)
    db.commit()

    result = {
        "url": url,
        "status_code": row.status_code,
        "latency_ms": row.latency_ms,
        "is_up": row.is_up,
        "attempts": attempts if is_up else 3
    }

    db.close()
    return result

async def async_save_check_result(url: str):
    now = datetime.utcnow()
    logging.info(f"[CHECKING] {url}")

    db = SessionLocal()
    start = time.time()

    try:
        res, attempts = await async_request_with_retry(url)
        latency = int((time.time() - start) * 1000)
        is_up = res.status_code == 200

        logging.info(f"[SUCCESS] {url} checked after {attempts} attempt(s)")

        row = CheckResult(
            url=url,
            status_code=res.status_code,
            latency_ms=latency,
            is_up=is_up
        )

    except httpx.RequestError:
        is_up = False

        row = CheckResult(
            url=url,
            status_code=None,
            latency_ms=None,
            is_up=False
        )

    last = (
        db.query(CheckResult)
        .filter(CheckResult.url == url)
        .order_by(CheckResult.id.desc())
        .first()
    )

    if last:
        if last.is_up and not is_up:
            if not last.last_alerted_at or (now - last.last_alerted_at > COOLDOWN):
                logging.error(f"[ALERT] {url} went DOWN")
                send_discord_alert(f"🚨 DOWN: {url}")
                row.last_alerted_at = now

        elif not last.is_up and is_up:
            logging.info(f"[RECOVER] {url} is back UP")
            send_discord_alert(f"✅ RECOVERED: {url}")

        else:
            logging.info(f"[NO CHANGE] {url} is still {'UP' if is_up else 'DOWN'}")
    else:
        logging.info(f"[FIRST CHECK] {url} is {'UP' if is_up else 'DOWN'}")

    if not is_up:
        logging.warning(f"[DOWN] {url} is down")

    db.add(row)
    db.commit()
    db.close()

def auto_check_targets():
    db = SessionLocal()
    rows = db.query(TargetModel).all()
    db.close()

    for target in rows:
        save_check_result(target.url)

async def auto_check_targets_async():
    db = SessionLocal()
    rows = db.query(TargetModel).all()
    db.close()

    await asyncio.gather(
        *(async_save_check_result(target.url) for target in rows)
    )
    
def run_auto_check_targets_async():
    asyncio.run(auto_check_targets_async())

def send_discord_alert(message: str):
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

    if not webhook_url:
        logging.warning("DISCORD_WEBHOOK_URL is not set")
        return

    try:
        requests.post(webhook_url, json={"content": message}, timeout=3)
    except requests.RequestException as e:
        logging.error(f"Failed to send Discord alert: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(run_auto_check_targets_async, "interval", seconds=10)
scheduler.start()
