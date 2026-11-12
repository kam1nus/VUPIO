"""Bounded background queue, persisted progress, independent of the audio bridge."""
import json
import queue
import threading
import time
import uuid


class Cancelled(Exception):
    pass


class Job:
    def __init__(self, owner, id):
        self.owner, self.id = owner, id
        self.cancelled = threading.Event()
    def check(self):
        if self.cancelled.is_set() or self.owner.closed.is_set():
            raise Cancelled('Operation cancelled')
    def update(self, progress, message):
        self.check()
        with self.owner.library.db() as db:
            db.execute('UPDATE ai_jobs SET progress=?, message=?, updated=? WHERE id=?',
                       (max(0,min(1,float(progress))),str(message)[:1000],time.time(),self.id))
    def publish(self,result):
        self.check()
        with self.owner.library.db() as db:
            db.execute('UPDATE ai_jobs SET result=?,updated=? WHERE id=?',
                       (json.dumps(result,ensure_ascii=False),time.time(),self.id))


class Jobs:
    def __init__(self, library):
        self.library=library
        self.queue=queue.Queue(maxsize=50)
        self.preview_queue=queue.Queue(maxsize=8)
        self.active={}
        self.lock=threading.Lock()
        self.closed=threading.Event()
        with library.db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS ai_jobs
                (id TEXT PRIMARY KEY, kind TEXT, status TEXT, progress REAL,
                 message TEXT, result TEXT, error TEXT, created REAL, updated REAL)''')
            db.execute("UPDATE ai_jobs SET status='cancelled', error='The app was closed' WHERE status IN ('queued','running')")
        self.workers=[threading.Thread(target=self._run,args=(pending,),daemon=True,name=name)
                      for pending,name in [(self.queue,'MIMIC-AI'),(self.preview_queue,'MIMIC-Preview')]]
        for worker in self.workers:worker.start()
    def submit(self, kind, function, *, preview=False):
        pending=self.preview_queue if preview else self.queue
        with self.lock:
            if pending.full():raise ValueError('Task queue full. Wait for tasks to finish.')
            id=uuid.uuid4().hex
            job=Job(self,id)
            with self.library.db() as db:
                db.execute('INSERT INTO ai_jobs VALUES (?,?,?,?,?,?,?,?,?)',
                           (id,kind,'queued',0,'Queued','{}','',time.time(),time.time()))
            self.active[id]=job
            pending.put_nowait((job,function))
        return {'job_id':id}
    def _run(self,pending):
        while not self.closed.is_set():
            try: job,fn=pending.get(timeout=.25)
            except queue.Empty: continue
            try:
                job.check()
                with self.library.db() as db: db.execute("UPDATE ai_jobs SET status='running' WHERE id=?",(job.id,))
                result=fn(job)
                job.check()
                with self.library.db() as db:
                    db.execute("UPDATE ai_jobs SET status='done',progress=1,message='Done',result=?,updated=? WHERE id=?",
                               (json.dumps(result,ensure_ascii=False),time.time(),job.id))
            except Exception as e:
                status='cancelled' if isinstance(e,Cancelled) else 'failed'
                detail={'error_code':e.code} if isinstance(getattr(e,'code',None),str) else {}
                with self.library.db() as db:
                    db.execute('UPDATE ai_jobs SET status=?,error=?,message=?,result=?,updated=? WHERE id=?',
                               (status,str(e)[:1800],str(e)[:1800],json.dumps(detail),time.time(),job.id))
            finally:
                with self.lock:self.active.pop(job.id,None)
                pending.task_done()
    def cancel(self,id):
        with self.lock:
            if id in self.active:self.active[id].cancelled.set()
    def snapshot(self,include_results=True):
        columns='*' if include_results else "id,kind,status,progress,message,'{}' AS result,error,created,updated"
        with self.library.db() as db: rows=db.execute('SELECT '+columns+' FROM ai_jobs ORDER BY created DESC LIMIT 100').fetchall()
        return [dict(dict(r),result=json.loads(r['result']) if include_results else {}) for r in rows]
    def get(self,id):
        with self.library.db() as db:row=db.execute('SELECT * FROM ai_jobs WHERE id=?',(id,)).fetchone()
        if not row:raise ValueError('Task not found')
        return dict(dict(row),result=json.loads(row['result']))
    def close(self):
        self.closed.set()
        with self.lock:
            for job in self.active.values():job.cancelled.set()
        for worker in self.workers:worker.join(timeout=2)
