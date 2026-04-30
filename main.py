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
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi import Request
import asyncio

task_queue = asyncio.Queue()

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

def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        pass

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

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

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
        <div class="card">
            <div class="card-header">
                <div class="name">
                    <a href="/dashboard/{target.id}" class="card-title-link">{target.name}</a>
                </div>
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

            <div class="actions">
                <a href="/targets/{target.id}/trend" class="text-link">View Trend</a>
            </div>
        </div>
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
                    color: inherit;
                }}

                .card-link {{
                    text-decoration: none;
                    color: inherit;
                    display: block;
                    margin-top: 0;
                }}

                .text-link {{
                    color: #4b0082;
                    text-decoration: underline;
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
            .card-title-link {{
                color: inherit;
                text-decoration: none;
            }}

            .card-title-link:hover {{
                text-decoration: underline;
            }}

            .text-link {{
                color: #4b0082;
                text-decoration: underline;
            }}

            .actions {{
                margin-top: 16px;
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
                <a href="/docs" class="text-link">API Docs</a>
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

@app.get("/stats")
def get_stats():
    db = SessionLocal()

    try:
        total_checks = db.query(CheckResult).count()
        up_count = db.query(CheckResult).filter(CheckResult.is_up == True).count()
        down_count = db.query(CheckResult).filter(CheckResult.is_up == False).count()

        average_latency = (
            db.query(func.avg(CheckResult.latency_ms))
            .filter(CheckResult.latency_ms != None)
            .scalar()
        )

        latest = db.query(CheckResult).order_by(CheckResult.id.desc()).first()

        return {
            "total_checks": total_checks,
            "up_count": up_count,
            "down_count": down_count,
            "latest_status": "up" if latest and latest.is_up else "down",
            "average_latency_ms": int(average_latency) if average_latency else None
        }

    finally:
        db.close()

@app.get("/checks")
def get_checks():
    db = SessionLocal()

    try:
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

    finally:
        db.close()

@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/queue")
def get_queue_status():
    return {
        "pending_jobs": task_queue.qsize(),
        "worker_count": 3
    }
@app.get("/targets")
def get_targets():
    db = SessionLocal()

    try:
        rows = db.query(TargetModel).order_by(TargetModel.id.desc()).all()

        return [
            {
                "id": row.id,
                "name": row.name,
                "url": row.url
            }
            for row in rows
        ]

    finally:
        db.close()

@app.get("/targets/{target_id}/trend", response_class=HTMLResponse)
def target_trend(target_id: int):
    db = SessionLocal()

    target = db.query(TargetModel).filter(TargetModel.id == target_id).first()

    if not target:
        return "<h1>Target not found</h1>"

    checks = (
        db.query(CheckResult)
        .filter(CheckResult.url == target.url)
        .order_by(CheckResult.id.desc())
        .limit(20)
        .all()
    )

    up_count = sum(1 for c in checks if c.is_up)
    uptime_percent = (up_count / len(checks) * 100) if checks else 0
    uptime = f"{uptime_percent:.1f}%" if checks else "N/A"

    if uptime_percent >= 95:
        uptime_color = "#16a34a"
    elif uptime_percent >= 80:
        uptime_color = "#f59e0b"
    else:
        uptime_color = "#dc2626"

    latencies = [c.latency_ms for c in checks if c.latency_ms is not None]
    avg_latency = int(sum(latencies) / len(latencies)) if latencies else None
    avg_latency_text = f"{avg_latency}ms" if avg_latency else "N/A"

    if avg_latency is None:
        latency_color = "#6b7280"
    elif avg_latency < 300:
        latency_color = "#16a34a"
    elif avg_latency < 800:
        latency_color = "#f59e0b"
    else:
        latency_color = "#dc2626"

    bars = []

    latency_points = []

    if latencies:
        max_latency = max(latencies)

        for c in reversed(checks):
            if c.latency_ms is None:
                height = 4
            else:
                height = max(4, int((c.latency_ms / max_latency) * 80))

            latency_points.append(f"""
            <div style="
                width: 10px;
                height: {height}px;
                background: #2563eb;
                border-radius: 3px;
                align-self: flex-end;
            "></div>
            """)

    for c in reversed(checks):
        color = "#16a34a" if c.is_up else "#dc2626"

        bars.append(f"""
        <div style="
            width: 10px;
            height: 40px;
            background: {color};
            border-radius: 3px;
        "></div>
        """)

    db.close()

    return f"""
    <html>
        <head>
            <title>Trend</title>
        </head>
        <body style="font-family: Arial; padding: 40px;">
            <h1>{target.name} - Uptime Trend</h1>
            <div style="display: flex; gap: 16px; margin: 24px 0;">  
                <div style="padding: 20px; border: 1px solid #ddd; border-radius: 14px;">
                    <div style="color: #777;">Uptime</div>
                    <div style="font-size: 42px; font-weight: bold; color: {uptime_color};">
                        {uptime}
                    </div>
                </div>

                <div style="padding: 20px; border: 1px solid #ddd; border-radius: 14px;">
                    <div style="color: #777;">Average Latency</div>
                    <div style="font-size: 42px; font-weight: bold; color: {latency_color};">
                        {avg_latency_text}
                    </div>
                </div>
            </div>

            <div style="display: flex; gap: 4px; margin-top: 20px;">
                {''.join(bars)}
            </div>

            <h2 style="margin-top: 40px;">Latency Trend</h2>

            <div style="
                display: flex;
                align-items: flex-end;
                gap: 4px;
                height: 90px;
                margin-top: 12px;
            ">
                {''.join(latency_points)}
            </div>

            <div style="margin-top: 20px;">
                <span style="color: #16a34a;">■ UP</span>
                <span style="color: #dc2626; margin-left: 20px;">■ DOWN</span>
            </div>

            <div style="margin-top: 30px;">
                <a href="/dashboard/{target.id}">← Back</a>
            </div>
        </body>
    </html>
    """


@app.post("/targets")
def add_target(target: Target):
    db = SessionLocal()
    
    existing = db.query(TargetModel).filter(TargetModel.url == target.url).first()

    if existing:
        raise HTTPException(status_code=400, detail="target url already exists")
    
    try:
        row = TargetModel(
            name=target.name,
            url=target.url
        )

        db.add(row)
        db.commit()
        db.refresh(row)

        return {
            "id": row.id,
            "name": row.name,
            "url": row.url
        }

    finally:
        db.close()

@app.post("/check")
@limiter.limit("10/minute")
def check_url(request: Request, url: str):
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



@app.on_event("startup")
async def start_workers():
    for i in range(3):
        asyncio.create_task(worker(i))

def request_with_retry(url: str, retries: int = 3, timeout: int = 3):
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, timeout=timeout, allow_redirects=True)
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
                response = await client.get(url, follow_redirects=True)
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

        logging.info({
            "event": "check_success",
            "url": url,
            "status_code": res.status_code,
            "latency_ms": latency,
            "attempts": attempts
        })

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
        logging.warning({
            "event": "check_failed",
            "url": url
        })

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

    logging.info({
        "event": "job_start",
        "target_count": len(rows)
    })

    if not rows:
        logging.info({
            "event": "job_empty"
        })
        return

    for target in rows:
        await task_queue.put(target.url)

    logging.info({
        "event": "job_enqueued",
        "target_count": len(rows)
    })
    
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

async def worker(worker_id: int):
    while True:
        url = await task_queue.get()

        logging.info({
            "event": "worker_processing",
            "worker_id": worker_id,
            "url": url
        })

        try:
            await async_save_check_result(url)
        finally:
            task_queue.task_done()