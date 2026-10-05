"""Explicit local checkpoint custody; never independent agency attestation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
from threading import RLock

from .contracts import canonical_bytes,validate_pin
from .store import StoreUnavailable,StoreConflict
from ..production_adapters import native


def _identity(info):
    return info.st_dev,info.st_ino


def _ordinary(path):
    path=Path(path).absolute()
    for parent in reversed((path,*path.parents)):
        info=parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or getattr(info,"st_file_attributes",0)&0x400:
            raise StoreUnavailable("Delivery checkpoint directory unavailable")


class FileCheckpointSink:
    """A monotonic same-host floor. Opening requires a separately known pin."""
    def __init__(self,root,initial_pin):
        self.root=Path(root).absolute();pin=validate_pin(initial_pin)
        _ordinary(self.root.parent);self.root.mkdir(exist_ok=False)
        self._root_identity=_identity(self.root.lstat());self._lock=RLock()
        self._files={};self._floor=pin
        self._write(pin)

    @classmethod
    def open(cls,root,*,expected_pin):
        self=object.__new__(cls);self.root=Path(root).absolute();_ordinary(self.root)
        self._root_identity=_identity(self.root.lstat());self._lock=RLock();self._files={}
        self._floor=validate_pin(expected_pin)
        current=self.read()
        expected=self.root/(str(self._floor["sequence"])+".json")
        if (not expected.exists() or validate_pin(json.loads(native._read(expected,65536)))!=self._floor
                or current["sequence"]<self._floor["sequence"]):
            raise StoreConflict("Delivery checkpoint restore is below required floor")
        self._floor=current
        return self

    def _paths(self):
        _ordinary(self.root)
        if _identity(self.root.lstat())!=self._root_identity:
            raise StoreUnavailable("Delivery checkpoint directory replaced")

    def read(self):
        with self._lock:
            self._paths();paths=list(self.root.iterdir())
            if not 1<=len(paths)<=4096:
                raise StoreUnavailable("Delivery checkpoint capacity unavailable")
            observed={}
            for path in paths:
                stem=path.stem
                if path.suffix!=".json" or not stem.isascii() or not stem.isdecimal() or str(int(stem))!=stem:
                    raise StoreUnavailable("Delivery checkpoint inventory invalid")
                before=path.lstat()
                if stat.S_ISLNK(before.st_mode) or getattr(before,"st_file_attributes",0)&0x400 or before.st_nlink!=1:
                    raise StoreUnavailable("Delivery checkpoint file unavailable")
                if path.name in self._files and self._files[path.name]!=_identity(before):
                    raise StoreUnavailable("Delivery checkpoint file replaced")
                raw=native._read(path,65536);pin=validate_pin(json.loads(raw))
                if (canonical_bytes(pin)+b"\n"!=raw or pin["sequence"]!=int(stem)
                        or pin["store_id"]!=self._floor["store_id"]):
                    raise StoreConflict("Delivery checkpoint identity changed")
                after=path.lstat()
                if _identity(before)!=_identity(after):
                    raise StoreUnavailable("Delivery checkpoint changed during read")
                observed[path.name]=_identity(after)
            if not self._files.keys()<=observed.keys():
                raise StoreUnavailable("Delivery checkpoint was removed")
            self._files=observed
            latest=max(paths,key=lambda p:int(p.stem))
            current=validate_pin(json.loads(native._read(latest,65536)))
            floor_path=self.root/(str(self._floor["sequence"])+".json")
            if (current["sequence"]<self._floor["sequence"] or not floor_path.exists()
                    or validate_pin(json.loads(native._read(floor_path,65536)))!=self._floor):
                raise StoreConflict("Delivery checkpoint rolled back or forked")
            self._paths()
            return dict(current)

    def _write(self,pin):
        self._paths();path=self.root/(str(pin["sequence"])+".json")
        raw=canonical_bytes(pin)+b"\n"
        with path.open("xb") as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        self._files[path.name]=_identity(path.lstat())
        self._paths()

    def __call__(self,pin):
        pin=validate_pin(pin)
        with self._lock:
            latest=self.read()
            if pin["store_id"]!=latest["store_id"] or pin["sequence"]<latest["sequence"]:
                raise StoreConflict("Delivery checkpoint cannot weaken its floor")
            if pin["sequence"]==latest["sequence"]:
                if pin!=latest:
                    raise StoreConflict("Delivery checkpoint fork refused")
            else:
                self._write(pin)
            self._floor=dict(pin)
            if self.read()!=pin:
                raise StoreUnavailable("Delivery checkpoint retention unavailable")
