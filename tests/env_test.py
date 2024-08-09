from __future__ import annotations
import os, sys
import pytest

def test_env():
    rad_gen_home = os.environ.get("RAD_GEN_HOME")
    assert os.path.isdir(rad_gen_home)


if __name__ == "__main__":
    test_env()