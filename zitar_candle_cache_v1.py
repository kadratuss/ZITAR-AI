"""Nonblocking, interval-specific candle cache. Never substitutes stale data."""
from concurrent.futures import ThreadPoolExecutor

DURATIONS={'5m':300000,'15m':900000,'1h':3600000}

class CandleCache:
    def __init__(self,fetch,intervals=('5m','15m','1h'),workers=2):
        self.fetch=fetch;self.intervals=intervals
        self.pool=ThreadPoolExecutor(max_workers=workers,thread_name_prefix='paper-candles')
        self.jobs={};self.rows={};self.errors={};self.retry_after={}

    def snapshot(self,symbols,ms):
        wanted={(s,i) for s in symbols for i in self.intervals}
        for key,job in list(self.jobs.items()):
            if key not in wanted and job.cancel():del self.jobs[key];continue
            if not job.done():continue
            del self.jobs[key]
            try:
                rows=job.result()
                if not isinstance(rows,list) or not rows:raise ValueError('EMPTY_CANDLES')
                if any(len(r)<7 for r in rows):raise ValueError('INVALID_CANDLES')
                self.rows[key]=rows;self.errors.pop(key,None)
                self.retry_after[key]=ms+5000
            except Exception as exc:
                self.errors[key]=type(exc).__name__+': '+str(exc);self.retry_after[key]=ms+15000
        for store in (self.rows,self.errors,self.retry_after):
            for key in list(store):
                if key not in wanted:del store[key]
        # Refresh only the interval that closed, 5m first; no repeated 1h downloads.
        result={s:{} for s in symbols}
        for interval in self.intervals:
            target=ms//DURATIONS[interval]*DURATIONS[interval]-1
            for symbol in symbols:
                key=(symbol,interval);rows=self.rows.get(key,[])
                ready=any(int(r[6])==target for r in rows)
                if ready:result[symbol][interval]=rows
                elif key not in self.jobs and ms>=self.retry_after.get(key,0):
                    # Never let a cached, still-forming candle become "closed"
                    # merely because the wall clock advanced after retrieval.
                    def closed_only(symbol=symbol,interval=interval,cutoff=ms):
                        return [r for r in self.fetch(symbol,interval) if len(r)>=7 and int(r[6])<cutoff]
                    self.jobs[key]=self.pool.submit(closed_only)
        return result

    def status(self,snapshot):
        return {'pending':len(self.jobs),'errors':{':'.join(k):v for k,v in self.errors.items()},
                'ready_intervals':sum(len(v) for v in snapshot.values()),
                'expected_intervals':len(snapshot)*len(self.intervals)}

    def close(self):self.pool.shutdown(wait=False,cancel_futures=True)
