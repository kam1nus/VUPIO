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
            raise Cancelled('Операция отменена')
    def update(self, progress, message):
        self.check()
        with self.owner.library.db() as db:
            db.execute('UPDATE ai_jobs SET progress=?, message=?, updated=? WHERE id=?',
                       (max(0,min(1,float(progress))),str(message)[:1000],time.time(),self.id))


class Jobs:
    def __init__(self, library):
        self.library=library
        self.queue=queue.Queue(maxsize=50)
        self.active={}
        self.closed=threading.Event()
        with library.db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS ai_jobs
                (id TEXT PRIMARY KEY, kind TEXT, status TEXT, progress REAL,
                 message TEXT, result TEXT, error TEXT, created REAL, updated REAL)''')
            db.execute("UPDATE ai_jobs SET status='cancelled', error='Приложение было закрыто' WHERE status IN ('queued','running')")
        self.worker=threading.Thread(target=self._run,daemon=True,name='MIMIC-AI')
        self.worker.start()
    def submit(self, kind, function):
        if self.queue.full(): raise ValueError('Очередь заполнена. Дождитесь завершения задач.')
        id=uuid.uuid4().hex
        job=Job(self,id)
        with self.library.db() as db:
            db.execute('INSERT INTO ai_jobs VALUES (?,?,?,?,?,?,?,?,?)',
                       (id,kind,'queued',0,'В очереди','{}','',time.time(),time.time()))
        self.active[id]=job
        self.queue.put_nowait((job,function))
        return {'job_id':id}
    def _run(self):
        while not self.closed.is_set():
            try: job,fn=self.queue.get(timeout=.25)
            except queue.Empty: continue
            try:
                job.check()
                with self.library.db() as db: db.execute("UPDATE ai_jobs SET status='running' WHERE id=?",(job.id,))
                result=fn(job)
                job.check()
                with self.library.db() as db:
                    db.execute("UPDATE ai_jobs SET status='done',progress=1,message='Готово',result=?,updated=? WHERE id=?",
                               (json.dumps(result,ensure_ascii=False),time.time(),job.id))
            except Exception as e:
                status='cancelled' if isinstance(e,Cancelled) else 'failed'
                with self.library.db() as db:
                    db.execute('UPDATE ai_jobs SET status=?,error=?,message=?,updated=? WHERE id=?',
                               (status,str(e)[:1800],str(e)[:1800],time.time(),job.id))
            finally:
                self.active.pop(job.id,None)
                self.queue.task_done()
    def cancel(self,id):
        if id in self.active: self.active[id].cancelled.set()
    def snapshot(self,include_results=True):
        columns='*' if include_results else "id,kind,status,progress,message,'{}' AS result,error,created,updated"
        with self.library.db() as db: rows=db.execute('SELECT '+columns+' FROM ai_jobs ORDER BY created DESC LIMIT 100').fetchall()
        return [dict(dict(r),result=json.loads(r['result']) if include_results else {}) for r in rows]
    def get(self,id):
        with self.library.db() as db:row=db.execute('SELECT * FROM ai_jobs WHERE id=?',(id,)).fetchone()
        if not row:raise ValueError('Задача не найдена')
        return dict(dict(row),result=json.loads(row['result']))
    def close(self):
        self.closed.set()
        for job in list(self.active.values()):job.cancelled.set()
        self.worker.join(timeout=2)
