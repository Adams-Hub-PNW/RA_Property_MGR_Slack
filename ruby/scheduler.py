"""Railway-friendly in-process scheduler (Pacific time). Every job skips weekends via day_of_week."""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from .config import TZ, SCHEDULE


def build(ruby) -> BackgroundScheduler:
    s = BackgroundScheduler(timezone=TZ)
    wd = "mon-fri"
    add = lambda fn, id, **kw: s.add_job(fn, CronTrigger(day_of_week=wd, timezone=TZ, **kw), id=id, misfire_grace_time=300)
    h, m = SCHEDULE["morning"];   add(ruby.morning, "morning", hour=h, minute=m)
    h, m = SCHEDULE["checkin_1"]; add(lambda: ruby.checkin("Check-in"), "checkin_1", hour=h, minute=m)
    h, m = SCHEDULE["checkin_2"]; add(lambda: ruby.checkin("Check-in"), "checkin_2", hour=h, minute=m)
    h, m = SCHEDULE["dar"];       add(ruby.dar_prompt, "dar", hour=h, minute=m)
    h, m = SCHEDULE["shutdown"];  add(ruby.shutdown, "shutdown", hour=h, minute=m)
    s.add_job(ruby.stuck_units, CronTrigger(day_of_week="mon,thu", hour=11, minute=0, timezone=TZ), id="stuck")
    s.add_job(ruby.friday_recap, CronTrigger(day_of_week="fri", hour=17, minute=0, timezone=TZ), id="friday")
    s.add_job(ruby.monthly_7th, CronTrigger(day="7", day_of_week=wd, hour=7, minute=0, timezone=TZ), id="d7")
    # 1st business day: first Mon-Fri run of the month
    s.add_job(ruby.monthly_inspections, CronTrigger(day="1-3", day_of_week="mon" , hour=7, minute=5, timezone=TZ), id="insp_mon")
    s.add_job(ruby.monthly_inspections, CronTrigger(day="1", day_of_week="tue-fri", hour=7, minute=5, timezone=TZ), id="insp_d1")
    s.add_job(ruby.store.retry_failed, CronTrigger(minute="*/15", timezone=TZ), id="retry")
    return s
