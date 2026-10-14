"""Independent SQLite project truth and durable run events."""
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException
from .capsule_models import Project, ProjectInput, Evidence, EvidenceInput, Task, TaskInput, TaskUpdate, Run, Snapshot

def now():
    return datetime.now(timezone.utc).isoformat()

def clean(value):
    if isinstance(value, dict):
        return {k:('[redacted]' if any(x in k.lower() for x in ('api_key','apikey','authorization','password')) else clean(v)) for k,v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, str):
        return re.sub(r'(?i)(api_key=|apikey=|bearer\s+)[^\s&"<>]+', r'\1[redacted]', value)
    return value

class Store:
    def __init__(self, path: Path):
        self.path=path
        path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL,kind TEXT NOT NULL,created_at TEXT NOT NULL,payload TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS events_run ON events(run_id,id);
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_run ON runs(project_id) WHERE status IN ('queued','running');
            ''')

    @contextmanager
    def db(self):
        con=sqlite3.connect(self.path,timeout=15)
        con.row_factory=sqlite3.Row
        try:
            with con: yield con
        finally: con.close()

    def projects(self):
        with self.db() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT payload FROM projects ORDER BY rowid DESC')]

    def project(self, pid):
        with self.db() as db:
            row=db.execute('SELECT payload FROM projects WHERE id=?',(pid,)).fetchone()
        if row is None: raise HTTPException(404,'项目不存在')
        return json.loads(row[0])

    def create_project(self, value: ProjectInput, pid=None):
        p=Project(**value.model_dump(),id=pid or str(uuid4()),created_at=now())
        with self.db() as db: db.execute('INSERT INTO projects VALUES(?,?)',(p.id,p.model_dump_json()))
        return p.model_dump()

    def rows(self, table, pid):
        assert table in ('evidence','tasks','runs')
        with self.db() as db:
            return [json.loads(r[0]) for r in db.execute(f'SELECT payload FROM {table} WHERE project_id=? ORDER BY rowid',(pid,))]

    def snapshot(self,pid):
        return Snapshot(project=self.project(pid),evidence=self.rows('evidence',pid),tasks=self.rows('tasks',pid),runs=self.rows('runs',pid))

    def add_evidence(self,pid,value:EvidenceInput,run_id=None):
        self.project(pid)
        e=Evidence(**value.model_dump(),id=str(uuid4()),project_id=pid,run_id=run_id,created_at=now())
        with self.db() as db: db.execute('INSERT INTO evidence VALUES(?,?,?)',(e.id,pid,e.model_dump_json()))
        if run_id: self.event(run_id,'evidence_saved',{'id':e.id,'title':e.title,'basis':e.basis})
        callback=getattr(self,'evidence_sink',None)
        if callback:
            try:callback(pid,e.model_dump())
            except Exception as ex:
                if run_id:self.event(run_id,'evidence_archive_pending',{'id':e.id,'error_type':type(ex).__name__})
        return e.model_dump()

    def add_task(self,pid,value:TaskInput):
        self.project(pid)
        t=Task(**value.model_dump(),id=str(uuid4()))
        with self.db() as db: db.execute('INSERT INTO tasks VALUES(?,?,?)',(t.id,pid,t.model_dump_json()))
        return t.model_dump()

    def update_task(self,pid,tid,value:TaskUpdate):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT payload FROM tasks WHERE id=? AND project_id=?',(tid,pid)).fetchone()
            if not row: raise HTTPException(404,'任务不存在')
            t=json.loads(row[0])
            if t['version']!=value.version: raise HTTPException(409,'任务已修改，请刷新后重试')
            t.update(value.model_dump());t['version']+=1
            db.execute('UPDATE tasks SET payload=? WHERE id=?',(json.dumps(t,ensure_ascii=False),tid))
        return t

    def create_run(self,pid,message):
        self.project(pid)
        r=Run(id=str(uuid4()),project_id=pid,message=message,status='queued',created_at=now())
        try:
            with self.db() as db: db.execute('INSERT INTO runs VALUES(?,?,?,?)',(r.id,pid,r.status,r.model_dump_json()))
        except sqlite3.IntegrityError: raise HTTPException(409,'该项目已有研究在运行')
        self.event(r.id,'request_received',{'message':message,'project_id':pid,'schema_version':'1.0'})
        return r.model_dump()

    def run(self,rid):
        with self.db() as db: row=db.execute('SELECT payload FROM runs WHERE id=?',(rid,)).fetchone()
        if not row: raise HTTPException(404,'运行不存在')
        return json.loads(row[0])

    def finish(self,rid,status,**values):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT payload FROM runs WHERE id=?',(rid,)).fetchone()
            r=json.loads(row[0]);r.update(values,status=status)
            validated=Run.model_validate(r)
            db.execute('UPDATE runs SET status=?,payload=? WHERE id=?',(status,validated.model_dump_json(),rid))
        self.event(rid,'run_status',{'status':status,**values})

    def event(self,rid,kind,payload):
        with self.db() as db: db.execute('INSERT INTO events(run_id,kind,created_at,payload) VALUES(?,?,?,?)',(rid,kind,now(),json.dumps(clean(payload),ensure_ascii=False,default=str)))

    def events(self,rid,after=0):
        with self.db() as db:
            return [{**dict(r),'payload':json.loads(r['payload'])} for r in db.execute('SELECT * FROM events WHERE run_id=? AND id>? ORDER BY id',(rid,after))]

    def recover(self):
        with self.db() as db: ids=[r[0] for r in db.execute("SELECT id FROM runs WHERE status IN ('queued','running')")]
        for rid in ids: self.finish(rid,'interrupted',error='服务重启中断了运行；已保存的证据仍在，可重新发起研究。')
