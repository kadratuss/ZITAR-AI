from pathlib import Path
import shutil
import subprocess

def main():
    shutil.copyfile('/srv/zitar/runtime/hosting/zitar-aux@.service','/etc/systemd/system/zitar-aux@.service')
    for task,minute in [('forward',2),('history',43),('intelligence',56),('liquidity',42)]:
        Path('/etc/systemd/system/zitar-aux-'+task+'.timer').write_text(
            '[Unit]\nDescription=ZITAR hourly '+task+'\n\n[Timer]\nOnCalendar=*-*-* *:'+str(minute).zfill(2)+':00 Europe/Istanbul\nPersistent=true\nUnit=zitar-aux@'+task+'.service\n\n[Install]\nWantedBy=timers.target\n')
    subprocess.run(['systemctl','daemon-reload'],check=True)
if __name__=='__main__':main()
