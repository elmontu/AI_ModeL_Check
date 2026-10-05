"""Ordinary bounded local fixture I/O, with generic errors and no overwrites."""
from __future__ import annotations
from functools import wraps
from pathlib import Path
import os
import stat
from .contracts import CapacityError,MAX_FILE_BYTES


def _generic(function):
    @wraps(function)
    def call(*args,**kwargs):
        try:
            return function(*args,**kwargs)
        except CapacityError:
            raise
        except (OSError,ValueError,TypeError):
            raise CapacityError("Capacity fixture I/O unavailable") from None
    return call


def _unsafe(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info,"st_file_attributes",0)&0x400)


def _identity(info):
    return info.st_dev,info.st_ino


def _version(info):
    return info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns


@_generic
def directory(path):
    path=Path(path).absolute()
    if ".." in path.parts or str(path).startswith(("//","\\\\", "\\\\?\\")):
        raise CapacityError("Capacity fixture path rejected")
    for part in (*reversed(path.parents),path):
        info=part.lstat()
        if _unsafe(info) or not stat.S_ISDIR(info.st_mode):
            raise CapacityError("Capacity fixture directory rejected")
    return path


@_generic
def fresh_directory(path):
    path=Path(path).absolute()
    parent=directory(path.parent)
    before=_identity(parent.lstat())
    path.mkdir(exist_ok=False)
    directory(path)
    if _identity(parent.lstat())!=before:
        raise CapacityError("Capacity fixture parent changed")
    return path


@_generic
def read_file(path,maxbytes=MAX_FILE_BYTES):
    if type(maxbytes) is not int or not 1<=maxbytes<=MAX_FILE_BYTES:
        raise CapacityError("Capacity fixture read bound rejected")
    path=Path(path).absolute()
    parent=directory(path.parent);parent_id=_identity(parent.lstat())
    before=path.lstat()
    def valid(info):
        return stat.S_ISREG(info.st_mode) and not _unsafe(info) and info.st_nlink==1 and 0<=info.st_size<=maxbytes
    if not valid(before):
        raise CapacityError("Capacity fixture file rejected")
    flags=os.O_RDONLY|getattr(os,"O_BINARY",0)|getattr(os,"O_NOFOLLOW",0)
    with os.fdopen(os.open(path,flags),"rb") as stream:
        opened=os.fstat(stream.fileno())
        if not valid(opened) or _version(opened)!=_version(before):
            raise CapacityError("Capacity fixture file changed")
        raw=stream.read(maxbytes+1)
        after=os.fstat(stream.fileno())
    directory(path.parent);final=path.lstat()
    if (not valid(final) or _version(opened)!=_version(after) or _version(after)!=_version(final)
            or len(raw)!=final.st_size or _identity(parent.lstat())!=parent_id):
        raise CapacityError("Capacity fixture read changed")
    return raw


@_generic
def exclusive_write(path,raw):
    if type(raw) is not bytes or len(raw)>MAX_FILE_BYTES:
        raise CapacityError("Capacity fixture write bound rejected")
    path=Path(path).absolute()
    parent=directory(path.parent);parent_id=_identity(parent.lstat())
    with path.open("xb") as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    if _identity(parent.lstat())!=parent_id or read_file(path)!=raw:
        raise CapacityError("Capacity fixture persistence changed")
    return path
