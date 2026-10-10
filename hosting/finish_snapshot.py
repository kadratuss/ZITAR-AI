"""Validate a completed staging archive before promotion; never copies live state."""
import argparse
import gzip
import hashlib
import tarfile
from pathlib import Path
def main():
    p=argparse.ArgumentParser();p.add_argument('partial');a=p.parse_args();partial=Path(a.partial)
    with gzip.open(partial,'rb') as stream:
        while stream.read(1024*1024):pass
    count=0
    with tarfile.open(partial,'r|gz') as archive:
        for member in archive:
            count+=1
            if member.isfile():
                stream=archive.extractfile(member)
                while stream.read(1024*1024):pass
    path=partial.with_suffix('');assert not path.exists();partial.replace(path)
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    path.with_suffix(path.suffix+'.sha256').write_text(digest+'  '+path.name+'\n')
    print(path.name,digest,count)
if __name__=='__main__':main()
