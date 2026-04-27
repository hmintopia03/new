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


@app.get("/")
def root():
    return {"msg": "uptime monitor is running"}

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

@app.get("/targets/{target_id}/stats")
def get_target_stats(target_id: int):
    db = SessionLocal()

    target = db.query(TargetModel).filter(TargetModel.id == target_id).first()

    if not target:
        db.close()
        return {"error": "target not found"}

    total_checks = (
        db.query(CheckResult)
        .filter(CheckResult.url == target.url)
        .count()
    )

    up_count = (
        db.query(CheckResult)
        .filter(CheckResult.url == target.url, CheckResult.is_up == True)
        .count()
    )

    down_count = total_checks - up_count

    average_latency = (
        db.query(func.avg(CheckResult.latency_ms))
        .filter(CheckResult.url == target.url, CheckResult.latency_ms != None)
        .scalar()
    )

    latest_checks = (
        db.query(CheckResult)
        .filter(CheckResult.url == target.url)
        .order_by(CheckResult.id.desc())
        .limit(10)
        .all()
    )

    db.close()

    return {
        "target": {
            "id": target.id,
            "name": target.name,
            "url": target.url
        },
        "total_checks": total_checks,
        "up_count": up_count,
        "down_count": down_count,
        "uptime_percentage": round((up_count / total_checks) * 100, 2) if total_checks > 0 else None,
        "average_latency_ms": int(average_latency) if average_latency else None,
        "latest_checks": [
            {
                "id": row.id,
                "status_code": row.status_code,
                "latency_ms": row.latency_ms,
                "is_up": row.is_up
            }
            for row in latest_checks
        ]
    }

@app.get("/stats")
def get_stats():
    db = SessionLocal()

    total_checks = db.query(CheckResult).count()

    up_count = (
        db.query(CheckResult)
        .filter(CheckResult.is_up == True)
        .count()
    )

    down_count = (
        db.query(CheckResult)
        .filter(CheckResult.is_up == False)
        .count()
    )

    average_latency = (
        db.query(func.avg(CheckResult.latency_ms))
        .filter(CheckResult.latency_ms != None)
        .scalar()
    )

    latest = (
        db.query(CheckResult)
        .order_by(CheckResult.id.desc())
        .first()
    )

    db.close()

    return {
        "total_checks": total_checks,
        "up_count": up_count,
        "down_count": down_count,
        "latest_status": "up" if latest and latest.is_up else "down",
        "average_latency_ms": int(average_latency) if average_latency else None
    }

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
        return {"error": "target not found"}

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

def save_check_result(url: str):
    logging.info(f"[CHECKING] {url}")

    db = SessionLocal()
    start = time.time()

    try:
        res = requests.get(url, timeout=5)
        latency = int((time.time() - start) * 1000)

        is_up = res.status_code == 200

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
            logging.error(f"[ALERT] {url} went DOWN")
            send_discord_alert(f"🚨 DOWN: {url}")

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
        "is_up": row.is_up
    }

    db.close()
    return result

def auto_check_targets():
    db = SessionLocal()
    rows = db.query(TargetModel).all()
    db.close()

    for target in rows:
        save_check_result(target.url)

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
scheduler.add_job(auto_check_targets, "interval", seconds=10)
scheduler.start()
